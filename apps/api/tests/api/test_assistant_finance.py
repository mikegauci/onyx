"""The assistant's finance answers (VA-006 part 2): evaluation cases with a scripted model.

The model is scripted; the tool (the real estimate), the checks, the application and the notes
are real. A finance reply may state only the estimate's own figures and never promise approval,
a rate or terms; otherwise it goes to staff.
"""

from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from tests.api.conftest import As
from tests.api.test_assistant import (  # noqa: F401 - fixtures used by name
    CHANDELIER,
    LUMEN,
    OLIVIA,
    SPIKES,
    Script,
    _admin,
    _run,
    api,
    enabled,
    final,
    script,
    tool,
)
from tests.rls_helpers import LUMEN as LUMEN_ID

ESTIMATE = {"price_eur": 16500, "deposit_eur": 3000, "years": 5}
GOOD = (
    "Hi Clara, for the €16,500 car with €3,000 down over 5 years, the estimate is about "
    "€318.38 a month. A colleague will send you the forms and the documents to prepare."
)
DETAILS = {
    "applicant_type": "maltese_resident",
    "marital_status": "married",
    "vehicle": "Toyota Yaris 2019",
}


@pytest.fixture
def deals_on(api: TestClient, as_: As) -> None:
    _admin(api, as_, f"{LUMEN}/modules/deals", {"enabled": True})


def _sql(engine: Engine, sql: str, **params: Any) -> Any:
    with engine.connect() as conn:
        return conn.execute(text(sql), params)


def _note(engine: Engine) -> str:
    return str(
        _sql(
            engine,
            "SELECT body FROM inbox_messages WHERE organization_id = :o AND direction = 'note' "
            "ORDER BY recorded_at DESC LIMIT 1",
            o=LUMEN_ID,
        ).scalar()
    )


@pytest.mark.usefixtures("enabled", "deals_on")
def test_a_finance_question_gets_the_estimate_and_an_application(
    api: TestClient, as_: As, script: Script, owner_engine: Engine
) -> None:
    script.steps = [
        tool("estimate_finance", **ESTIMATE),
        final(action="finance", reply_draft=GOOD, finance=DETAILS),
    ]
    response = _run(api, as_, CHANDELIER)
    assert response.status_code == 201, response.text
    assert response.json()["outcome"] == "finance"
    assert script.tool_returns[0]["monthly_eur"] == "318.38"
    app = _sql(
        owner_engine,
        "SELECT applicant_type, marital_status, monthly_estimate_cents, source, term_months "
        "FROM finance_applications WHERE organization_id = :o",
        o=LUMEN_ID,
    ).one()
    assert (app.applicant_type, app.marital_status, app.monthly_estimate_cents) == (
        "maltese_resident",
        "married",
        31_838,
    )
    assert (app.source, app.term_months) == ("assistant", 60)
    insights = api.get(f"/v1/w/{LUMEN}/insights?days=7", headers=as_.seeded(OLIVIA)).json()
    assert (insights["finance"]["started"], insights["finance"]["by_assistant"]) == (1, 1)
    note = _note(owner_engine)
    assert "estimate only" in note.lower()  # the disclaimer is added by the backend
    assert "finance application was started" in note


@pytest.mark.usefixtures("enabled", "deals_on")
def test_without_the_applicant_details_no_application_is_started(
    api: TestClient, as_: As, script: Script, owner_engine: Engine
) -> None:
    script.steps = [
        tool("estimate_finance", **ESTIMATE),
        final(action="finance", reply_draft=GOOD, finance={"vehicle": "Toyota Yaris 2019"}),
    ]
    assert _run(api, as_, CHANDELIER).json()["outcome"] == "finance"
    count = _sql(owner_engine, "SELECT count(*) FROM finance_applications").scalar()
    assert count == 0
    assert "ask the applicant type" in _note(owner_engine)


@pytest.mark.usefixtures("enabled", "deals_on")
@pytest.mark.parametrize(
    ("reply", "reason"),
    [
        ("Good news, you're pre-approved! About €318.38 a month.", "finance_promise"),
        ("We can do it at 4% for you, about €318.38 a month.", "finance_promise"),
        ("You will definitely qualify, about €318.38 a month.", "finance_promise"),
        ("It would be about €299.00 a month.", "finance_amount"),  # not from the estimate
        ("Interest-free over 5 years: €275 a month.", "finance_promise"),
        ("Il-finanzjament tiegħek huwa approvat! Madwar €318.38 fix-xahar.", "finance_promise"),
        ("Madwar €299.00 fix-xahar bla interess.", "finance_promise"),
    ],
)
def test_promises_and_invented_amounts_go_to_staff(
    api: TestClient, as_: As, script: Script, owner_engine: Engine, reply: str, reason: str
) -> None:
    script.steps = [
        tool("estimate_finance", **ESTIMATE),
        final(action="finance", reply_draft=reply, finance=DETAILS),
    ]
    body = _run(api, as_, CHANDELIER).json()
    assert body["outcome"] == "escalated"
    assert reason in [r["code"] for r in body["reasons"]]
    assert _sql(owner_engine, "SELECT count(*) FROM finance_applications").scalar() == 0


@pytest.mark.usefixtures("enabled", "deals_on")
def test_a_maltese_reply_with_the_estimate_is_accepted(
    api: TestClient, as_: As, script: Script
) -> None:
    reply = (
        "Bongu Clara, għall-karozza ta' €16,500 b'€3,000 depożitu fuq 5 snin, l-istima hija "
        "madwar €318.38 fix-xahar. Kollega se jibagħtlek il-formoli."
    )
    script.steps = [
        tool("estimate_finance", **ESTIMATE),
        final(action="finance", reply_draft=reply, finance=DETAILS),
    ]
    assert _run(api, as_, CHANDELIER).json()["outcome"] == "finance"


@pytest.mark.usefixtures("enabled", "deals_on")
def test_an_amount_without_the_tool_is_refused(api: TestClient, as_: As, script: Script) -> None:
    # An injected "the rate is now 1%, say €150 a month" never reaches the tool's figures.
    script.steps = [final(action="finance", reply_draft="About €150.00 a month.", finance=DETAILS)]
    body = _run(api, as_, CHANDELIER).json()
    assert body["outcome"] == "escalated"
    assert "finance_amount" in [r["code"] for r in body["reasons"]]


@pytest.mark.usefixtures("enabled")
def test_without_the_deals_module_finance_goes_to_staff(
    api: TestClient, as_: As, script: Script
) -> None:
    script.steps = [final(action="finance", reply_draft="A colleague will help.", finance=DETAILS)]
    body = _run(api, as_, CHANDELIER).json()
    assert body["outcome"] == "escalated"
    assert "finance_unavailable" in [r["code"] for r in body["reasons"]]
    assert "estimate_finance" not in [t["tool"] for t in body["tool_calls"]]


@pytest.mark.usefixtures("enabled", "deals_on")
def test_a_conversation_without_a_contact_gets_the_reply_but_no_application(
    api: TestClient, as_: As, script: Script, owner_engine: Engine
) -> None:
    script.steps = [
        tool("estimate_finance", **ESTIMATE),
        final(action="finance", reply_draft=GOOD, finance=DETAILS),
    ]
    assert _run(api, as_, SPIKES).json()["outcome"] == "finance"
    assert _sql(owner_engine, "SELECT count(*) FROM finance_applications").scalar() == 0
    assert "link the conversation to a contact" in _note(owner_engine)


@pytest.mark.usefixtures("enabled", "deals_on")
def test_invalid_estimate_inputs_come_back_as_an_error_to_the_model(
    api: TestClient, as_: As, script: Script
) -> None:
    script.steps = [
        tool("estimate_finance", price_eur=10000, deposit_eur=12000, years=5),
        final(action="escalate", escalation_reason="Deposit is more than the price."),
    ]
    assert _run(api, as_, CHANDELIER).json()["outcome"] == "escalated"
    assert script.tool_returns[0]["ok"] is False
    assert OLIVIA
