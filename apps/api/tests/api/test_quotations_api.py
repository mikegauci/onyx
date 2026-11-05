"""Quotations API: drafting, exact totals, stale data, approval, versions, outcomes and PDF."""

import re
from datetime import date, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from app.core.db.seed import seed_id
from app.modules.quotations.pricing import LineInput, quote_totals
from tests.api.conftest import As
from tests.rls_helpers import LUMEN as LUMEN_ID
from tests.rls_helpers import OLIVIA

ADAM = "adam.admin@lumen.example.test"
MIA = "mia.member@lumen.example.test"
LUMEN = "lumen-lighting-test"
BASE = f"/v1/w/{LUMEN}/quotations"

SEEDED = seed_id(f"{LUMEN}:quote:Q-2026-0001")
CLARA = seed_id(f"{LUMEN}:contact:clara.borg@seaview.example.test")
LUCA = seed_id(f"{LUMEN}:contact:luca.vella@example.test")
SEAVIEW = seed_id(f"{LUMEN}:customer:Seaview Hotel (test)")
CHANDELIER_LEAD = seed_id(f"{LUMEN}:lead:Lobby chandelier replacement")
GARDEN_LEAD = seed_id(f"{LUMEN}:lead:Garden lighting enquiry")
ARC_30 = seed_id(f"{LUMEN}:sku:ARC-P-30-BRS")
RETAIL = seed_id(f"{LUMEN}:price-list:RETAIL")
STANDARD = seed_id(f"{LUMEN}:vat:STANDARD")
ZERO = seed_id(f"{LUMEN}:vat:ZERO")


class Caller:
    def __init__(self, api: TestClient, headers: dict[str, str]) -> None:
        self.api, self.headers = api, headers

    def get(self, path: str, **params: Any) -> Any:
        return self.api.get(f"{BASE}{path}", params=params, headers=self.headers)

    def post(self, path: str, body: dict[str, Any] | None = None) -> Any:
        return self.api.post(f"{BASE}{path}", json=body or {}, headers=self.headers)

    def patch(self, path: str, body: dict[str, Any]) -> Any:
        return self.api.patch(f"{BASE}{path}", json=body, headers=self.headers)

    def put(self, path: str, body: dict[str, Any]) -> Any:
        return self.api.put(f"{BASE}{path}", json=body, headers=self.headers)

    def delete(self, path: str) -> Any:
        return self.api.delete(f"{BASE}{path}", headers=self.headers)


@pytest.fixture
def olivia(api: TestClient, as_: As) -> Caller:
    return Caller(api, as_.seeded(OLIVIA))


@pytest.fixture
def adam(api: TestClient, as_: As) -> Caller:
    return Caller(api, as_.seeded(ADAM))


@pytest.fixture
def mia(api: TestClient, as_: As) -> Caller:
    return Caller(api, as_.seeded(MIA))


def _new_quote(caller: Caller, **overrides: Any) -> Any:
    response = caller.post(
        "/quotes", {"title": "Garden lights", "contact_id": str(LUCA), **overrides}
    )
    assert response.status_code == 201, response.text
    return response.json()


def _sku_line(caller: Caller, quote_id: str, sku: str, **extra: Any) -> Any:
    return caller.post(f"/quotes/{quote_id}/lines", {"kind": "catalogue", "sku": sku, **extra})


def _approve(caller: Caller, quote: dict[str, Any], *, acknowledge_all: bool = True) -> Any:
    acknowledge = [
        {"line_id": w["line_id"], "code": w["code"]}
        for w in quote["warnings"]
        if acknowledge_all and not w["blocking"]
    ]
    return caller.post(
        f"/quotes/{quote['id']}/approve",
        {"version": quote["version"], "acknowledge": acknowledge},
    )


# --- reading the seeded draft ----------------------------------------------------------------


def test_seeded_draft_has_exact_totals(olivia: Caller) -> None:
    quote = olivia.get(f"/quotes/{SEEDED}").json()
    assert (quote["number"], quote["status"], quote["version"]) == ("Q-2026-0001", "draft", 1)
    assert quote["contact"]["label"] == "Clara Borg"
    assert quote["customer"]["label"] == "Seaview Hotel (test)"
    assert quote["lead"]["label"] == "Lobby chandelier replacement"
    assert quote["prices_include_vat"] is True
    assert [(x["sku"], x["quantity"], x["gross"]["amount"]) for x in quote["lines"]] == [
        ("ARC-P-30-BRS", 2, "258.00"),
        (None, 1, "80.00"),
    ]
    totals = quote["totals"]
    assert (totals["net"]["amount"], totals["vat"]["amount"], totals["gross"]["amount"]) == (
        "286.44",
        "51.56",
        "338.00",
    )
    assert totals["vat_breakdown"] == [
        {
            "code": "STANDARD",
            "rate_percent": "18.00",
            "net": {"minor": 28644, "amount": "286.44"},
            "vat": {"minor": 5156, "amount": "51.56"},
        }
    ]
    assert quote["warnings"] == []
    assert quote["allowed_actions"] == ["approve", "cancel", "edit"]
    listed = olivia.get("/quotes").json()["items"]
    assert [(q["number"], q["gross"]["amount"]) for q in listed] == [("Q-2026-0001", "338.00")]


# --- drafting --------------------------------------------------------------------------------


def test_member_drafts_a_quote_with_catalogue_and_custom_lines(mia: Caller) -> None:
    quote = _new_quote(mia)
    assert re.fullmatch(r"Q-\d{4}-\d{4}", quote["number"])
    assert quote["number"] != "Q-2026-0001"
    assert (quote["customer"], quote["price_list"]["id"]) == (None, str(RETAIL))
    assert quote["lines"] == []

    added = _sku_line(mia, quote["id"], "arc-p-30-brs", quantity=3)
    assert added.status_code == 201, added.text
    line = added.json()["lines"][0]
    assert (line["sku"], line["unit_price"]["amount"], line["vat_code"]) == (
        "ARC-P-30-BRS",
        "129.00",
        "STANDARD",
    )
    assert line["description"] == "Arc pendant light - 30 cm, brass"

    custom = mia.post(
        f"/quotes/{quote['id']}/lines",
        {
            "kind": "custom",
            "description": "Delivery to Gozo",
            "unit_price": "45",
            "vat_rate_id": str(ZERO),
        },
    )
    assert custom.status_code == 201, custom.text
    body = custom.json()
    assert body["lines"][1]["gross"]["amount"] == "45.00"
    assert body["totals"]["gross"]["amount"] == "432.00"  # 3 x 129.00 + 45.00

    patched = mia.patch(f"/quotes/{quote['id']}/lines/{line['id']}", {"quantity": 1})
    assert patched.json()["totals"]["gross"]["amount"] == "174.00"
    removed = mia.delete(f"/quotes/{quote['id']}/lines/{body['lines'][1]['id']}")
    assert [x["sku"] for x in removed.json()["lines"]] == ["ARC-P-30-BRS"]


@pytest.mark.parametrize(
    ("body", "loc"),
    [
        ({"kind": "catalogue", "sku": "GSP-7W-3000K"}, ["body", "variant_id"]),  # no price
        ({"kind": "catalogue", "sku": "NOPE-1"}, ["body", "sku"]),
        ({"kind": "catalogue"}, ["body", "variant_id"]),
        (
            {"kind": "catalogue", "sku": "ARC-P-30-BRS", "quantity": 0},
            ["body", "catalogue", "quantity"],
        ),
        (
            {"kind": "custom", "description": "x", "unit_price": "1.234", "vat_rate_id": str(ZERO)},
            ["body", "custom", "unit_price"],
        ),
        ({"kind": "free", "sku": "ARC-P-30-BRS"}, ["body"]),
    ],
)
def test_invalid_lines_are_rejected(mia: Caller, body: dict[str, Any], loc: list[str]) -> None:
    quote = _new_quote(mia)
    response = mia.post(f"/quotes/{quote['id']}/lines", body)
    assert response.status_code == 422, response.text
    assert response.json()["error"]["details"][0]["loc"][: len(loc)] == loc


def test_discounts_above_the_limit_need_an_approver(mia: Caller, adam: Caller) -> None:
    quote = _new_quote(mia)
    over = _sku_line(mia, quote["id"], "ARC-P-30-BRS", discount_percent="15")
    assert over.status_code == 422
    assert over.json()["error"]["details"][0]["type"] == "above_limit"
    assert _sku_line(mia, quote["id"], "ARC-P-30-BRS", discount_percent="10").status_code == 201
    assert _sku_line(adam, quote["id"], "ARC-P-30-BRS", discount_percent="15").status_code == 201


@pytest.mark.parametrize(
    ("overrides", "loc"),
    [
        ({"lead_id": str(CHANDELIER_LEAD)}, ["body", "lead_id"]),  # Clara's lead, not Luca's
        ({"contact_id": "00000000-0000-0000-0000-000000000000"}, ["body", "contact_id"]),
        ({"price_list_id": str(STANDARD)}, ["body", "price_list_id"]),
        ({"customer_id": str(LUCA)}, ["body", "customer_id"]),
    ],
)
def test_invalid_quotes_are_rejected(
    mia: Caller, overrides: dict[str, Any], loc: list[str]
) -> None:
    response = mia.post("/quotes", {"title": "x", "contact_id": str(LUCA), **overrides})
    assert response.status_code == 422, response.text
    assert response.json()["error"]["details"][0]["loc"] == loc


def test_customer_defaults_to_the_contacts(mia: Caller) -> None:
    quote = _new_quote(mia, contact_id=str(CLARA), lead_id=str(CHANDELIER_LEAD))
    assert quote["customer"]["id"] == str(SEAVIEW)
    assert quote["lead"]["id"] == str(CHANDELIER_LEAD)


# --- stale data and approval -----------------------------------------------------------------


def test_stock_warnings_must_be_acknowledged(mia: Caller, adam: Caller) -> None:
    quote = _new_quote(mia)
    _sku_line(mia, quote["id"], "ARC-P-45-BLK")  # stock 0
    quote = _sku_line(mia, quote["id"], "GSP-7W-4000K").json()  # stock unknown
    codes = sorted((w["code"], w["blocking"]) for w in quote["warnings"])
    assert codes == [("out_of_stock", False), ("stock_unknown", False)]

    assert _approve(mia, quote).status_code == 403
    refused = _approve(adam, quote, acknowledge_all=False)
    assert refused.status_code == 409
    assert {d["type"] for d in refused.json()["error"]["details"]} == {
        "out_of_stock",
        "stock_unknown",
    }
    approved = _approve(adam, quote)
    assert approved.status_code == 200, approved.text
    body = approved.json()
    assert (body["status"], body["version_status"]) == ("approved", "approved")
    assert body["approved_by"]["label"] == "Adam Admin"
    assert {w["code"] for w in body["acknowledged_warnings"]} == {"out_of_stock", "stock_unknown"}
    assert date.fromisoformat(body["valid_until"]) >= date.today() + timedelta(days=29)
    assert body["allowed_actions"] == ["accept", "cancel", "decline", "revise"]


def test_a_changed_price_blocks_approval_until_the_line_is_refreshed(
    olivia: Caller, owner_engine: Engine
) -> None:
    with owner_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO catalogue_prices "
                "(organization_id, variant_id, price_list_id, amount_minor, valid_from) "
                "VALUES (:org, :variant, :list, 13900, now())"
            ),
            {"org": LUMEN_ID, "variant": ARC_30, "list": RETAIL},
        )
    quote = olivia.get(f"/quotes/{SEEDED}").json()
    [warning] = quote["warnings"]
    assert (warning["code"], warning["blocking"], warning["current"]) == (
        "price_changed",
        True,
        {"unit_price_minor": 13900},
    )
    # The quote keeps its snapshot until someone decides.
    assert quote["totals"]["gross"]["amount"] == "338.00"
    blocked = _approve(olivia, quote)
    assert blocked.status_code == 409
    assert blocked.json()["error"]["details"][0]["type"] == "price_changed"

    line_id = warning["line_id"]
    refreshed = olivia.post(f"/quotes/{SEEDED}/lines/{line_id}/refresh").json()
    assert refreshed["warnings"] == []
    assert refreshed["totals"]["gross"]["amount"] == "358.00"  # 2 x 139.00 + 80.00
    assert _approve(olivia, refreshed).status_code == 200


def test_approval_needs_the_current_version_and_lines(olivia: Caller, mia: Caller) -> None:
    quote = olivia.get(f"/quotes/{SEEDED}").json()
    stale = olivia.post(f"/quotes/{SEEDED}/approve", {"version": 2, "acknowledge": []})
    assert stale.status_code == 409
    empty = _new_quote(mia)
    assert _approve(olivia, empty).status_code == 409
    assert _approve(olivia, quote).status_code == 200


def test_approved_totals_are_stored_and_reproduce_exactly(
    olivia: Caller, owner_engine: Engine
) -> None:
    quote = olivia.get(f"/quotes/{SEEDED}").json()
    assert _approve(olivia, quote).status_code == 200
    with owner_engine.connect() as conn:
        stored = conn.execute(
            text(
                "SELECT net_minor, vat_minor, gross_minor, prices_include_vat "
                "FROM quotations_versions WHERE quote_id = :q AND version = 1"
            ),
            {"q": SEEDED},
        ).one()
        lines = conn.execute(
            text(
                "SELECT unit_price_minor, quantity, discount_percent, vat_code, vat_percent "
                "FROM quotations_lines l JOIN quotations_versions v ON v.id = l.version_id "
                "WHERE v.quote_id = :q AND v.version = 1"
            ),
            {"q": SEEDED},
        ).all()
    recomputed = quote_totals((LineInput(*row) for row in lines), prices_include_vat=stored[3])
    assert (recomputed.net_minor, recomputed.vat_minor, recomputed.gross_minor) == tuple(stored[:3])
    assert recomputed.gross_minor == 33800


# --- after approval --------------------------------------------------------------------------


def test_approved_quotes_are_frozen_and_revised_as_new_versions(
    olivia: Caller, owner_engine: Engine
) -> None:
    quote = olivia.get(f"/quotes/{SEEDED}").json()
    approved = _approve(olivia, quote).json()
    line_id = approved["lines"][0]["id"]
    assert olivia.patch(f"/quotes/{SEEDED}/lines/{line_id}", {"quantity": 5}).status_code == 409
    assert olivia.patch(f"/quotes/{SEEDED}", {"title": "x"}).status_code == 409

    revised = olivia.post(f"/quotes/{SEEDED}/revise")
    assert revised.status_code == 200, revised.text
    v2 = revised.json()
    assert (v2["status"], v2["version"], v2["version_status"]) == ("draft", 2, "draft")
    assert [v["version"] for v in v2["versions"]] == [2, 1]
    assert v2["versions"][1]["status"] == "superseded"
    new_line = v2["lines"][0]["id"]
    assert new_line != line_id
    edited = olivia.patch(f"/quotes/{SEEDED}/lines/{new_line}", {"quantity": 3}).json()
    assert edited["totals"]["gross"]["amount"] == "467.00"

    v1 = olivia.get(f"/quotes/{SEEDED}/versions/1").json()
    assert (v1["version_status"], v1["totals"]["gross"]["amount"]) == ("superseded", "338.00")
    assert v1["allowed_actions"] == []
    with owner_engine.connect() as conn:
        quantities = conn.execute(
            text(
                "SELECT v.version, l.quantity FROM quotations_lines l "
                "JOIN quotations_versions v ON v.id = l.version_id "
                "WHERE v.quote_id = :q AND l.kind = 'catalogue' ORDER BY v.version"
            ),
            {"q": SEEDED},
        ).all()
    assert [tuple(r) for r in quantities] == [(1, 2), (2, 3)]


def test_outcomes_and_cancellation(olivia: Caller, mia: Caller, owner_engine: Engine) -> None:
    quote = olivia.get(f"/quotes/{SEEDED}").json()
    assert olivia.post(f"/quotes/{SEEDED}/outcome", {"outcome": "accepted"}).status_code == 409
    _approve(olivia, quote)
    accepted = mia.post(f"/quotes/{SEEDED}/outcome", {"outcome": "accepted"})
    assert accepted.status_code == 200
    assert (accepted.json()["status"], accepted.json()["allowed_actions"]) == ("accepted", [])
    assert mia.post(f"/quotes/{SEEDED}/cancel").status_code == 409

    other = _new_quote(mia)
    cancelled = mia.post(f"/quotes/{other['id']}/cancel", {"reason": "Customer went elsewhere"})
    assert cancelled.json()["status"] == "cancelled"
    assert cancelled.json()["outcome_reason"] == "Customer went elsewhere"


def test_an_expired_quote_cannot_be_accepted(olivia: Caller, owner_engine: Engine) -> None:
    quote = olivia.get(f"/quotes/{SEEDED}").json()
    _approve(olivia, quote)
    with owner_engine.begin() as conn:
        # Test-only: step past the freeze trigger to simulate time passing.
        conn.execute(
            text("ALTER TABLE quotations_versions DISABLE TRIGGER quotations_versions_frozen")
        )
        conn.execute(
            text(
                "UPDATE quotations_versions SET valid_until = current_date - 1 WHERE quote_id = :q"
            ),
            {"q": SEEDED},
        )
        conn.execute(
            text("ALTER TABLE quotations_versions ENABLE TRIGGER quotations_versions_frozen")
        )
    expired = olivia.post(f"/quotes/{SEEDED}/outcome", {"outcome": "accepted"})
    assert expired.status_code == 409
    assert "expired" in expired.json()["error"]["message"]
    declined = olivia.post(f"/quotes/{SEEDED}/outcome", {"outcome": "declined", "reason": "Late"})
    assert declined.json()["status"] == "declined"


# --- PDF, settings, audit --------------------------------------------------------------------


def test_pdf_preview(olivia: Caller) -> None:
    draft = olivia.get(f"/quotes/{SEEDED}/versions/1/pdf")
    assert draft.status_code == 200
    assert draft.headers["content-type"] == "application/pdf"
    assert draft.headers["cache-control"] == "no-store"
    assert 'filename="Q-2026-0001-v1.pdf"' in draft.headers["content-disposition"]
    assert draft.content.startswith(b"%PDF-")
    quote = olivia.get(f"/quotes/{SEEDED}").json()
    _approve(olivia, quote)
    approved = olivia.get(f"/quotes/{SEEDED}/versions/1/pdf")
    assert approved.content.startswith(b"%PDF-")
    assert approved.content != draft.content  # the watermark is gone
    assert olivia.get(f"/quotes/{SEEDED}/versions/9/pdf").status_code == 404


def test_settings(mia: Caller, adam: Caller) -> None:
    assert mia.get("/settings").json() == {
        "number_prefix": "Q",
        "validity_days": 30,
        "max_discount_percent": "10.00",
    }
    assert mia.put("/settings", {"validity_days": 14}).status_code == 403
    updated = adam.put(
        "/settings", {"number_prefix": "LUM", "validity_days": 14, "max_discount_percent": "20"}
    )
    assert updated.status_code == 200, updated.text
    assert adam.put("/settings", {"number_prefix": "lum"}).status_code == 422
    quote = _new_quote(mia)
    assert quote["number"].startswith("LUM-")
    assert _sku_line(mia, quote["id"], "ARC-P-30-BRS", discount_percent="15").status_code == 201


def test_changes_are_audited(olivia: Caller, owner_engine: Engine) -> None:
    quote = olivia.get(f"/quotes/{SEEDED}").json()
    _approve(olivia, quote)
    olivia.post(f"/quotes/{SEEDED}/revise")
    with owner_engine.connect() as conn:
        actions = (
            conn.execute(
                text(
                    "SELECT action FROM audit_entries WHERE organization_id = :o "
                    "AND action LIKE 'quotations.%' ORDER BY occurred_at, id"
                ),
                {"o": LUMEN_ID},
            )
            .scalars()
            .all()
        )
    assert actions == ["quotations.quote.approved", "quotations.quote.revised"]


def test_unknown_quote_and_line_are_404(olivia: Caller, mia: Caller) -> None:
    missing = "00000000-0000-0000-0000-000000000000"
    assert olivia.get(f"/quotes/{missing}").status_code == 404
    other = _new_quote(mia)
    seeded_line = olivia.get(f"/quotes/{SEEDED}").json()["lines"][0]["id"]
    # A line of another quote is not found through this one.
    assert mia.delete(f"/quotes/{other['id']}/lines/{seeded_line}").status_code == 404
