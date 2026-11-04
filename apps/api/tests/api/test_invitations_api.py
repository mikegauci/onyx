"""Invitation scaffolding: create (admin+), accept (matching email, single use, unexpired)."""

import uuid

from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from tests.api.conftest import As

OLIVIA = "olivia.owner@lumen.example.test"
ADAM = "adam.admin@lumen.example.test"
MIA = "mia.member@lumen.example.test"
HUGO = "hugo.owner@harbour.example.test"
LUMEN = "lumen-lighting-test"
HARBOUR = "harbour-catering-test"
INVITEE = "new.hire@lumen.example.test"


def _invite(api: TestClient, headers: dict[str, str], role: str = "member", **kw: str) -> str:
    response = api.post(
        f"/w/{kw.get('slug', LUMEN)}/invitations",
        json={"email": kw.get("email", INVITEE), "role": role},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    token: str = response.json()["token"]
    return token


def test_admin_invites_and_invitee_joins(api: TestClient, as_: As, owner_engine: Engine) -> None:
    token = _invite(api, as_.seeded(ADAM))
    invitee = as_.subject(uuid.uuid4(), INVITEE)

    accepted = api.post("/invitations/accept", json={"token": token}, headers=invitee)
    assert accepted.status_code == 200, accepted.text
    assert (accepted.json()["slug"], accepted.json()["role"]) == (LUMEN, "member")
    me = api.get("/me", headers=invitee).json()
    assert [w["slug"] for w in me["workspaces"]] == [LUMEN]

    with owner_engine.connect() as conn:
        stored = conn.execute(text("SELECT token_hash FROM invitations")).scalar_one()
        actions = conn.execute(text("SELECT action FROM audit_entries ORDER BY action")).scalars()
        assert token not in stored
        assert len(stored) == 64
        assert list(actions) == ["invitation.accepted", "invitation.created", "membership.created"]


def test_invitation_is_single_use(api: TestClient, as_: As) -> None:
    token = _invite(api, as_.seeded(ADAM))
    invitee = as_.subject(uuid.uuid4(), INVITEE)
    assert (
        api.post("/invitations/accept", json={"token": token}, headers=invitee).status_code == 200
    )
    assert (
        api.post("/invitations/accept", json={"token": token}, headers=invitee).status_code == 410
    )


def test_invitation_for_another_email_is_not_found(api: TestClient, as_: As) -> None:
    token = _invite(api, as_.seeded(ADAM))
    stranger = as_.subject(uuid.uuid4(), "someone.else@example.test")
    assert (
        api.post("/invitations/accept", json={"token": token}, headers=stranger).status_code == 404
    )
    # A member of another tenant cannot use it either.
    hugo = as_.seeded(HUGO)
    assert api.post("/invitations/accept", json={"token": token}, headers=hugo).status_code == 404


def test_expired_invitation_is_gone(api: TestClient, as_: As, owner_engine: Engine) -> None:
    token = _invite(api, as_.seeded(ADAM))
    with owner_engine.begin() as conn:
        conn.execute(text("UPDATE invitations SET expires_at = now() - interval '1 minute'"))
    invitee = as_.subject(uuid.uuid4(), INVITEE)
    assert (
        api.post("/invitations/accept", json={"token": token}, headers=invitee).status_code == 410
    )


def test_unknown_token_is_not_found(api: TestClient, as_: As) -> None:
    response = api.post("/invitations/accept", json={"token": "x" * 43}, headers=as_.seeded(MIA))
    assert response.status_code == 404


def test_existing_member_cannot_accept_again(api: TestClient, as_: As) -> None:
    token = _invite(api, as_.seeded(OLIVIA), email=MIA)
    response = api.post("/invitations/accept", json={"token": token}, headers=as_.seeded(MIA))
    assert response.status_code == 409


def test_member_cannot_invite(api: TestClient, as_: As) -> None:
    response = api.post(f"/w/{LUMEN}/invitations", json={"email": INVITEE}, headers=as_.seeded(MIA))
    assert response.status_code == 403


def test_only_owners_invite_owners(api: TestClient, as_: As) -> None:
    body = {"email": INVITEE, "role": "owner"}
    assert (
        api.post(f"/w/{LUMEN}/invitations", json=body, headers=as_.seeded(ADAM)).status_code == 403
    )
    assert (
        api.post(f"/w/{LUMEN}/invitations", json=body, headers=as_.seeded(OLIVIA)).status_code
        == 201
    )


def test_cannot_invite_into_another_tenant(api: TestClient, as_: As) -> None:
    response = api.post(
        f"/w/{HARBOUR}/invitations", json={"email": INVITEE}, headers=as_.seeded(OLIVIA)
    )
    assert response.status_code == 404


def test_invalid_email_is_rejected(api: TestClient, as_: As) -> None:
    response = api.post(
        f"/w/{LUMEN}/invitations", json={"email": "not-an-email"}, headers=as_.seeded(ADAM)
    )
    assert response.status_code == 422
