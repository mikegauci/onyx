"""AI gateway against a real database, with a scripted model (no network, no spend).

Covers usage attribution, fail-closed budgets, the alert threshold, retries/timeouts/invalid
output, redaction of prompts/replies/keys, concurrent reservations, frozen usage events and
two-tenant isolation through the API and directly in SQL.
"""

import asyncio
import logging
import uuid
from collections.abc import Callable, Iterator
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient
from pydantic_ai.exceptions import ModelQuotaExceededError, ModelRateLimitError
from pydantic_ai.messages import ModelMessage, ModelResponse, ToolCallPart
from pydantic_ai.models import Model
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.usage import RequestUsage
from sqlalchemy import Engine, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.ai.errors import AIBudgetExceededError
from app.ai.gateway import AIGateway, AIResult
from app.ai.providers import ModelRef, price_for, resolve_model
from app.api.ai import DIAGNOSTIC_INSTRUCTIONS, DIAGNOSTIC_PROMPT, DiagnosticReply
from app.core.config import Settings
from app.core.db.seed import seed_id
from app.main import create_app
from tests.api.conftest import As
from tests.auth_tokens import TokenFactory
from tests.rls_helpers import HARBOUR as HARBOUR_ID
from tests.rls_helpers import LUMEN as LUMEN_ID
from tests.rls_helpers import SAM, as_role

LUMEN = "lumen-lighting-test"
HARBOUR = "harbour-catering-test"
PAT = "pat.platform@onyx.example.test"
OLIVIA = "olivia.owner@lumen.example.test"
MIA = "mia.member@lumen.example.test"
HUGO = "hugo.owner@harbour.example.test"

KEY = "sk-test-not-a-real-key-7f3a"
LEAK = "LEAK-provider-echo-of-prompt-91c2"
PRICE = {"input_usd_per_mtok": "2.00", "output_usd_per_mtok": "10.00"}
# The scripted model reports 100 input and 20 output tokens per request: 200 + 200 micro-USD.
COST_PER_REQUEST = 400


class Script:
    """A model whose replies are scripted per request: ok, bad, rate_limit, quota, slow, boom."""

    def __init__(self) -> None:
        self.steps: list[str] = []
        self.calls = 0

    async def reply(self, messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        self.calls += 1
        step = self.steps.pop(0) if self.steps else "ok"
        usage = RequestUsage(input_tokens=100, output_tokens=20)
        tool = info.output_tools[0].name
        if step == "slow":
            await asyncio.sleep(2)
        elif step == "slow_ok":
            await asyncio.sleep(0.3)
        elif step == "rate_limit":
            raise ModelRateLimitError("scripted", f"rate limited: {LEAK}")
        elif step == "quota":
            raise ModelQuotaExceededError("scripted", f"quota: {LEAK}")
        elif step == "boom":
            raise RuntimeError(LEAK)
        elif step == "bad":
            return ModelResponse(parts=[ToolCallPart(tool, {"status": "nope"})], usage=usage)
        return ModelResponse(
            parts=[ToolCallPart(tool, {"status": "ok", "echo": "onyx"})], usage=usage
        )

    def factory(self, ref: ModelRef, settings: Settings) -> Model:
        return FunctionModel(self.reply, model_name=ref.name)


def ai_settings(**overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "environment": "test",
        "cors_origins": ["http://localhost:3001"],
        "ai_default_model": "fake:scripted",
        "ai_model_prices": {"fake:scripted": PRICE},
        "ai_retry_backoff_seconds": 0,
        "ai_timeout_seconds": 1,
        "ai_max_output_tokens": 200,
        "openai_api_key": KEY,
        "anthropic_api_key": KEY,
    }
    return Settings(_env_file=None, **(values | overrides))


def worst_case(settings: Settings) -> int:
    gateway = AIGateway(cast(async_sessionmaker[AsyncSession], None), settings)
    price = price_for(settings, resolve_model(settings, "diagnostic"))
    return gateway.worst_case_cost_micros(
        price, DiagnosticReply, DIAGNOSTIC_INSTRUCTIONS, DIAGNOSTIC_PROMPT
    )


@pytest.fixture
def script() -> Script:
    return Script()


MakeApi = Callable[..., TestClient]


@pytest.fixture
def make_api(db_url: str, tokens: TokenFactory, script: Script) -> Iterator[MakeApi]:
    clients: list[TestClient] = []

    def _make(**overrides: Any) -> TestClient:
        engine = create_async_engine(db_url, poolclass=NullPool)
        app = create_app(
            ai_settings(**overrides),
            token_verifier=tokens.verifier(),
            session_factory=async_sessionmaker(engine, expire_on_commit=False),
            ai_model_factory=script.factory,
        )
        client = TestClient(app)
        client.__enter__()
        clients.append(client)
        return client

    yield _make
    for client in clients:
        client.__exit__(None, None, None)


@pytest.fixture
def ai_api(make_api: MakeApi) -> TestClient:
    return make_api()


def _budget(api: TestClient, as_: As, slug: str, limit: int, alert: int = 80) -> None:
    response = api.put(
        f"/v1/admin/organizations/{slug}/ai-budget",
        json={"monthly_limit_usd_micros": limit, "alert_percent": alert},
        headers=as_.seeded(PAT),
    )
    assert response.status_code == 200, response.text


def _test_call(api: TestClient, as_: As, slug: str = LUMEN) -> Any:
    return api.post(f"/v1/admin/organizations/{slug}/ai/test-call", headers=as_.seeded(PAT))


def _events(engine: Engine, org: uuid.UUID) -> list[Any]:
    with engine.connect() as conn:
        return list(
            conn.execute(
                text(
                    "SELECT * FROM ai_usage_events WHERE organization_id = :o ORDER BY created_at"
                ),
                {"o": org},
            )
        )


# --- budgets (platform admin) ----------------------------------------------------------------


def test_platform_admin_sets_and_reads_a_budget(
    ai_api: TestClient, as_: As, owner_engine: Engine
) -> None:
    _budget(ai_api, as_, LUMEN, 2_000_000, alert=75)
    body = ai_api.get(f"/v1/admin/organizations/{LUMEN}/ai-budget", headers=as_.seeded(PAT)).json()
    assert body["monthly_limit_usd_micros"] == 2_000_000
    assert body["alert_percent"] == 75
    assert body["spent_usd_micros"] == 0
    with owner_engine.connect() as conn:
        audit = conn.execute(
            text("SELECT metadata FROM audit_entries WHERE action = 'ai.budget.updated'")
        ).scalar_one()
    assert audit["monthly_limit_usd_micros"] == 2_000_000


def test_budget_without_a_row_reads_as_unset(ai_api: TestClient, as_: As) -> None:
    body = ai_api.get(
        f"/v1/admin/organizations/{HARBOUR}/ai-budget", headers=as_.seeded(PAT)
    ).json()
    assert body["monthly_limit_usd_micros"] is None
    assert body["spent_usd_micros"] == 0


@pytest.mark.parametrize(
    "body",
    [
        {"monthly_limit_usd_micros": -1},
        {"monthly_limit_usd_micros": 10_000 * 1_000_000 + 1},
        {"monthly_limit_usd_micros": 1, "alert_percent": 0},
        {"monthly_limit_usd_micros": 1, "alert_percent": 101},
        {"monthly_limit_usd_micros": 1.5},
    ],
)
def test_budget_input_is_validated(ai_api: TestClient, as_: As, body: dict[str, Any]) -> None:
    response = ai_api.put(
        f"/v1/admin/organizations/{LUMEN}/ai-budget", json=body, headers=as_.seeded(PAT)
    )
    assert response.status_code == 422


@pytest.mark.parametrize("email", [OLIVIA, MIA, HUGO])
def test_budget_and_test_call_are_platform_admin_only(
    ai_api: TestClient, as_: As, script: Script, email: str
) -> None:
    headers = as_.seeded(email)
    base = f"/v1/admin/organizations/{LUMEN}"
    assert ai_api.get(f"{base}/ai-budget", headers=headers).status_code == 404
    put = ai_api.put(f"{base}/ai-budget", json={"monthly_limit_usd_micros": 1}, headers=headers)
    assert put.status_code == 404
    assert ai_api.post(f"{base}/ai/test-call", headers=headers).status_code == 404
    assert script.calls == 0


def test_unknown_organisation_is_not_found(ai_api: TestClient, as_: As) -> None:
    headers = as_.seeded(PAT)
    assert ai_api.get("/v1/admin/organizations/nope/ai-budget", headers=headers).status_code == 404
    assert (
        ai_api.post("/v1/admin/organizations/nope/ai/test-call", headers=headers).status_code == 404
    )


# --- fail-closed budget enforcement ----------------------------------------------------------


def test_no_budget_blocks_before_any_provider_call(
    ai_api: TestClient, as_: As, script: Script, owner_engine: Engine
) -> None:
    response = _test_call(ai_api, as_)
    assert response.status_code == 429
    assert response.json()["error"]["code"] == "budget_exceeded"
    assert script.calls == 0
    [event] = _events(owner_engine, LUMEN_ID)
    assert (event.status, event.cost_usd_micros, event.attempts) == ("budget_blocked", 0, 0)


def test_call_runs_on_the_server_and_is_attributed_to_the_tenant(
    ai_api: TestClient, as_: As, owner_engine: Engine
) -> None:
    _budget(ai_api, as_, LUMEN, 1_000_000)
    response = _test_call(ai_api, as_)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["reply"] == {"status": "ok", "echo": "onyx"}
    assert (body["provider"], body["model"]) == ("fake", "scripted")
    assert (body["input_tokens"], body["output_tokens"]) == (100, 20)
    assert body["cost_usd_micros"] == COST_PER_REQUEST
    assert body["attempts"] == 1

    [event] = _events(owner_engine, LUMEN_ID)
    assert event.status == "succeeded"
    assert event.id == uuid.UUID(body["event_id"])
    assert event.cost_usd_micros == COST_PER_REQUEST
    assert event.actor_user_id == seed_id(PAT)
    assert event.workload == "diagnostic"
    assert event.finished_at is not None
    assert _events(owner_engine, HARBOUR_ID) == []


def test_reservation_larger_than_the_remaining_budget_is_refused(
    ai_api: TestClient, as_: As, script: Script
) -> None:
    reserve = worst_case(ai_settings())
    _budget(ai_api, as_, LUMEN, reserve - 1)
    assert _test_call(ai_api, as_).status_code == 429
    assert script.calls == 0

    _budget(ai_api, as_, LUMEN, reserve)
    assert _test_call(ai_api, as_).status_code == 200
    # The finished call recorded its real cost, so less than a full reservation remains.
    assert _test_call(ai_api, as_).status_code == 429
    assert script.calls == 1


def test_zero_budget_disables_ai(ai_api: TestClient, as_: As, script: Script) -> None:
    _budget(ai_api, as_, LUMEN, 0)
    assert _test_call(ai_api, as_).status_code == 429
    assert script.calls == 0


def test_alert_threshold_fires_once_per_month(
    ai_api: TestClient, as_: As, owner_engine: Engine, caplog: pytest.LogCaptureFixture
) -> None:
    reserve = worst_case(ai_settings())
    _budget(ai_api, as_, LUMEN, reserve * 4, alert=25)
    with caplog.at_level(logging.INFO):
        assert _test_call(ai_api, as_).status_code == 200
        assert _test_call(ai_api, as_).status_code == 200
    alerts = [r for r in caplog.records if r.getMessage() == "ai budget alert threshold reached"]
    assert len(alerts) == 1
    assert alerts[0].levelno == logging.WARNING
    with owner_engine.connect() as conn:
        alerted = conn.execute(
            text("SELECT alerted_period FROM ai_budgets WHERE organization_id = :o"),
            {"o": LUMEN_ID},
        ).scalar_one()
    assert alerted is not None
    assert alerted.day == 1


def test_concurrent_calls_cannot_overspend(
    db_url: str, script: Script, owner_engine: Engine
) -> None:
    settings = ai_settings(ai_timeout_seconds=5)
    reserve = worst_case(settings)
    with owner_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO ai_budgets (organization_id, monthly_limit_usd_micros) "
                "VALUES (:o, :limit)"
            ),
            {"o": LUMEN_ID, "limit": reserve + reserve // 2},  # room for one call, not two
        )
    script.steps = ["slow_ok", "slow_ok"]

    async def _run() -> list[AIResult[DiagnosticReply] | BaseException]:
        engine = create_async_engine(db_url, poolclass=NullPool)
        gateway = AIGateway(
            async_sessionmaker(engine, expire_on_commit=False),
            settings,
            model_factory=script.factory,
        )

        async def _one() -> AIResult[DiagnosticReply]:
            return await gateway.run_structured(
                organization_id=LUMEN_ID,
                workload="diagnostic",
                output_type=DiagnosticReply,
                instructions=DIAGNOSTIC_INSTRUCTIONS,
                prompt=DIAGNOSTIC_PROMPT,
            )

        try:
            return list(await asyncio.gather(_one(), _one(), return_exceptions=True))
        finally:
            await engine.dispose()

    results = asyncio.run(_run())
    assert sum(isinstance(r, AIResult) for r in results) == 1
    assert sum(isinstance(r, AIBudgetExceededError) for r in results) == 1
    assert sorted(e.status for e in _events(owner_engine, LUMEN_ID)) == [
        "budget_blocked",
        "succeeded",
    ]


# --- provider failures -----------------------------------------------------------------------


def test_transient_error_is_retried(
    ai_api: TestClient, as_: As, script: Script, owner_engine: Engine
) -> None:
    _budget(ai_api, as_, LUMEN, 1_000_000)
    script.steps = ["rate_limit", "ok"]
    response = _test_call(ai_api, as_)
    assert response.status_code == 200, response.text
    assert response.json()["attempts"] == 2
    [event] = _events(owner_engine, LUMEN_ID)
    assert (event.status, event.attempts) == ("succeeded", 2)


def test_non_retryable_error_fails_after_one_attempt(
    ai_api: TestClient, as_: As, script: Script, owner_engine: Engine
) -> None:
    _budget(ai_api, as_, LUMEN, 1_000_000)
    script.steps = ["quota"]
    response = _test_call(ai_api, as_)
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "unavailable"
    assert script.calls == 1
    [event] = _events(owner_engine, LUMEN_ID)
    assert (event.status, event.attempts, event.error_kind) == (
        "provider_error",
        1,
        "ModelQuotaExceededError",
    )
    assert event.cost_usd_micros == 0  # the reservation is released: nothing was billed


def test_retries_are_bounded(
    ai_api: TestClient, as_: As, script: Script, owner_engine: Engine
) -> None:
    _budget(ai_api, as_, LUMEN, 1_000_000)
    script.steps = ["rate_limit"] * 10
    assert _test_call(ai_api, as_).status_code == 503
    assert script.calls == 3
    [event] = _events(owner_engine, LUMEN_ID)
    assert (event.status, event.attempts) == ("provider_error", 3)


def test_timeout_is_recorded(
    make_api: MakeApi, as_: As, script: Script, owner_engine: Engine
) -> None:
    api = make_api(ai_timeout_seconds=0.05, ai_max_attempts=2)
    _budget(api, as_, LUMEN, 1_000_000)
    script.steps = ["slow", "slow"]
    assert _test_call(api, as_).status_code == 503
    [event] = _events(owner_engine, LUMEN_ID)
    assert (event.status, event.attempts) == ("timeout", 2)


def test_output_that_fails_validation_is_rejected_and_still_metered(
    ai_api: TestClient, as_: As, script: Script, owner_engine: Engine
) -> None:
    _budget(ai_api, as_, LUMEN, 1_000_000)
    script.steps = ["bad", "bad"]
    assert _test_call(ai_api, as_).status_code == 503
    [event] = _events(owner_engine, LUMEN_ID)
    assert event.status == "invalid_output"
    assert (event.input_tokens, event.output_tokens) == (200, 40)
    assert event.cost_usd_micros == 2 * COST_PER_REQUEST


def test_one_bad_reply_is_corrected_by_the_output_retry(
    ai_api: TestClient, as_: As, script: Script
) -> None:
    _budget(ai_api, as_, LUMEN, 1_000_000)
    script.steps = ["bad", "ok"]
    response = _test_call(ai_api, as_)
    assert response.status_code == 200, response.text
    assert response.json()["cost_usd_micros"] == 2 * COST_PER_REQUEST


def test_prompts_replies_and_keys_never_reach_logs_errors_or_storage(
    ai_api: TestClient,
    as_: As,
    script: Script,
    owner_engine: Engine,
    caplog: pytest.LogCaptureFixture,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _budget(ai_api, as_, LUMEN, 1_000_000)
    script.steps = ["rate_limit", "boom"]
    with caplog.at_level(logging.DEBUG):
        response = _test_call(ai_api, as_)
        script.steps = ["ok"]
        ok = _test_call(ai_api, as_)
    assert response.status_code == 503
    assert ok.status_code == 200
    logged = caplog.text + "".join(str(vars(r)) for r in caplog.records) + capsys.readouterr().out
    stored = "".join(str(tuple(e)) for e in _events(owner_engine, LUMEN_ID))
    for secret in (LEAK, KEY, DIAGNOSTIC_PROMPT, DIAGNOSTIC_INSTRUCTIONS, '"echo"'):
        assert secret not in logged
        assert secret not in response.text
        assert secret not in stored
    assert "RuntimeError" in stored  # only the error's class name is kept


# --- tenant usage API ------------------------------------------------------------------------


def test_owner_sees_usage_and_remaining_budget(ai_api: TestClient, as_: As) -> None:
    _budget(ai_api, as_, LUMEN, 1_000_000)
    assert _test_call(ai_api, as_).status_code == 200
    body = ai_api.get(f"/v1/w/{LUMEN}/ai/usage", headers=as_.seeded(OLIVIA)).json()
    assert body["monthly_limit_usd_micros"] == 1_000_000
    assert body["spent_usd_micros"] == COST_PER_REQUEST
    assert body["remaining_usd_micros"] == 1_000_000 - COST_PER_REQUEST
    [event] = body["events"]
    assert event["status"] == "succeeded"
    assert set(event) >= {"input_tokens", "output_tokens", "cost_usd_micros", "model"}
    assert not {"prompt", "reply", "output", "actor_user_id"} & set(event)


def test_members_cannot_read_ai_usage(ai_api: TestClient, as_: As) -> None:
    response = ai_api.get(f"/v1/w/{LUMEN}/ai/usage", headers=as_.seeded(MIA))
    assert response.status_code == 403


def test_usage_never_crosses_tenants(ai_api: TestClient, as_: As) -> None:
    _budget(ai_api, as_, LUMEN, 1_000_000)
    assert _test_call(ai_api, as_).status_code == 200
    for email in (HUGO, SAM):  # Sam is admin of Harbour and member of Lumen
        body = ai_api.get(f"/v1/w/{HARBOUR}/ai/usage", headers=as_.seeded(email)).json()
        assert body["events"] == []
        assert body["spent_usd_micros"] == 0
        assert body["monthly_limit_usd_micros"] is None
    # A Harbour owner naming Lumen gets nothing at all.
    assert ai_api.get(f"/v1/w/{LUMEN}/ai/usage", headers=as_.seeded(HUGO)).status_code == 404
    assert ai_api.get(f"/v1/w/{LUMEN}/ai/usage", headers=as_.seeded(SAM)).status_code == 403


# --- database guarantees ---------------------------------------------------------------------


def _insert_event(conn: Any, org: uuid.UUID, status: str = "succeeded") -> uuid.UUID:
    return cast(
        uuid.UUID,
        conn.execute(
            text(
                "INSERT INTO ai_usage_events (organization_id, workload, provider, model, status) "
                "VALUES (:o, 'diagnostic', 'fake', 'scripted', :s) RETURNING id"
            ),
            {"o": org, "s": status},
        ).scalar_one(),
    )


def test_finalised_events_are_frozen_and_never_deleted(owner_engine: Engine) -> None:
    with owner_engine.begin() as conn:
        done = _insert_event(conn, LUMEN_ID)
        reserved = _insert_event(conn, LUMEN_ID, "reserved")
    with pytest.raises(DBAPIError), owner_engine.begin() as conn:
        conn.execute(
            text("UPDATE ai_usage_events SET cost_usd_micros = 0 WHERE id = :i"), {"i": done}
        )
    with pytest.raises(DBAPIError), owner_engine.begin() as conn:
        conn.execute(text("DELETE FROM ai_usage_events WHERE id = :i"), {"i": reserved})
    with owner_engine.begin() as conn:  # a reservation is finalised exactly once
        conn.execute(
            text("UPDATE ai_usage_events SET status = 'succeeded' WHERE id = :i"), {"i": reserved}
        )
    with pytest.raises(DBAPIError), owner_engine.begin() as conn:
        conn.execute(
            text("UPDATE ai_usage_events SET status = 'timeout' WHERE id = :i"), {"i": reserved}
        )


def test_rls_scopes_ai_tables_to_the_bound_tenant(owner_engine: Engine) -> None:
    with owner_engine.begin() as conn:
        _insert_event(conn, LUMEN_ID)
        _insert_event(conn, HARBOUR_ID)
        conn.execute(
            text(
                "INSERT INTO ai_budgets (organization_id, monthly_limit_usd_micros) "
                "VALUES (:l, 5), (:h, 7)"
            ),
            {"l": LUMEN_ID, "h": HARBOUR_ID},
        )
    with as_role(owner_engine, "onyx_app", email=SAM, organization_id=HARBOUR_ID) as conn:
        orgs = set(conn.execute(text("SELECT organization_id FROM ai_usage_events")).scalars())
        limits = set(
            conn.execute(text("SELECT monthly_limit_usd_micros FROM ai_budgets")).scalars()
        )
    assert orgs == {HARBOUR_ID}
    assert limits == {7}
    with as_role(owner_engine, "onyx_worker", organization_id=HARBOUR_ID) as conn:
        assert set(conn.execute(text("SELECT organization_id FROM ai_usage_events")).scalars()) == {
            HARBOUR_ID
        }


def test_worker_cannot_write_another_tenants_usage(owner_engine: Engine) -> None:
    with (
        pytest.raises(DBAPIError),
        as_role(owner_engine, "onyx_worker", organization_id=HARBOUR_ID) as conn,
    ):
        _insert_event(conn, LUMEN_ID, "reserved")


def test_app_role_cannot_write_usage_or_budgets(owner_engine: Engine) -> None:
    with (
        pytest.raises(DBAPIError),
        as_role(owner_engine, "onyx_app", email=SAM, organization_id=HARBOUR_ID) as conn,
    ):
        _insert_event(conn, HARBOUR_ID, "reserved")
    with (
        pytest.raises(DBAPIError),
        as_role(owner_engine, "onyx_app", email=SAM, organization_id=HARBOUR_ID) as conn,
    ):
        conn.execute(
            text(
                "INSERT INTO ai_budgets (organization_id, monthly_limit_usd_micros) "
                "VALUES (:h, 999999999)"
            ),
            {"h": HARBOUR_ID},
        )
