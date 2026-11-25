"""The assistant notes the cars a customer asked about and what they want (VA-005 part 2).

The model is scripted; the tools and what they store are real. Suggestions stay unconfirmed
and match nothing until staff confirm them.
"""

from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from app.core.db.seed import seed_id
from tests.api.conftest import As
from tests.api.test_assistant import (  # noqa: F401 - fixtures used by name
    CHANDELIER,
    LUMEN,
    MIA,
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

LEAD = seed_id(f"{LUMEN}:lead:Lobby chandelier replacement")
CLARA = seed_id(f"{LUMEN}:contact:clara.borg@seaview.example.test")
ESCALATE = {"action": "escalate", "escalation_reason": "A person should follow up."}


@pytest.fixture
def cars_on(api: TestClient, as_: As, owner_engine: Engine) -> None:
    _admin(api, as_, f"{LUMEN}/modules/catalogue", {"enabled": True})
    _admin(api, as_, f"{LUMEN}/modules/automotive", {"enabled": True})
    with owner_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO automotive_vehicles (organization_id, source_ref, title, make, "
                "model, year, price_cents, status) VALUES (:o, 'g1', 'Volkswagen Golf 2019', "
                "'Volkswagen', 'Golf', 2019, 1650000, 'available')"
            ),
            {"o": LUMEN_ID},
        )


def _rows(engine: Engine, sql: str) -> list[Any]:
    with engine.connect() as conn:
        return list(conn.execute(text(sql), {"o": LUMEN_ID}).all())


@pytest.mark.usefixtures("enabled", "cars_on")
def test_cars_found_and_criteria_stated_are_noted_for_staff(
    api: TestClient, as_: As, script: Script, owner_engine: Engine
) -> None:
    script.steps = [
        tool("search_vehicles", query="Golf"),
        tool("suggest_wanted", make="Volkswagen", max_price_eur=18000),
        final(**ESCALATE),
    ]
    assert _run(api, as_, CHANDELIER).status_code == 201
    [interest] = _rows(
        owner_engine,
        "SELECT contact_id, source, conversation_id FROM automotive_interests "
        "WHERE organization_id = :o",
    )
    assert (interest.contact_id, interest.source, interest.conversation_id) == (
        CLARA,
        "assistant",
        CHANDELIER,
    )

    # Asked again with a new budget: the open suggestion is updated, not duplicated.
    script.steps = [
        tool("suggest_wanted", make="Volkswagen", max_price_eur=20000),
        final(**ESCALATE),
    ]
    assert _run(api, as_, CHANDELIER).status_code == 201
    [wanted] = api.get(
        f"/v1/w/{LUMEN}/automotive/leads/{LEAD}/wanted", headers=as_.seeded(MIA)
    ).json()["items"]
    assert (wanted["source"], wanted["confirmed"], wanted["price_max_cents"]) == (
        "assistant",
        False,
        2_000_000,
    )
    assert wanted["pending_matches"] == 0  # unconfirmed: matches nothing yet


@pytest.mark.usefixtures("enabled", "cars_on")
def test_a_suggestion_with_nothing_stated_stores_nothing(
    api: TestClient, as_: As, script: Script, owner_engine: Engine
) -> None:
    script.steps = [tool("suggest_wanted"), final(**ESCALATE)]
    assert _run(api, as_, CHANDELIER).status_code == 201
    assert script.tool_returns[0]["ok"] is False
    assert _rows(owner_engine, "SELECT id FROM automotive_wanted WHERE organization_id = :o") == []
