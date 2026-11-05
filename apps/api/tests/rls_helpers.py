"""Enter the RLS-restricted roles directly in SQL, as the API and workers do."""

import uuid
from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Connection, Engine, text

from app.core.db.seed import seed_auth_subject, seed_id

OLIVIA = "olivia.owner@lumen.example.test"  # Lumen owner
HUGO = "hugo.owner@harbour.example.test"  # Harbour owner
SAM = "sam.consultant@onyx.example.test"  # member of both
LUMEN = seed_id("lumen-lighting-test")
HARBOUR = seed_id("harbour-catering-test")


@contextmanager
def as_role(
    engine: Engine,
    role: str,
    *,
    email: str | None = None,
    organization_id: uuid.UUID | None = None,
) -> Iterator[Connection]:
    with engine.connect() as conn, conn.begin():
        conn.execute(text(f"SET LOCAL ROLE {role}"))
        if email is not None:
            conn.execute(
                text("SELECT set_config('app.current_auth_subject', :s, true)"),
                {"s": str(seed_auth_subject(email))},
            )
        if organization_id is not None:
            conn.execute(
                text("SELECT set_config('app.current_organization_id', :o, true)"),
                {"o": str(organization_id)},
            )
        yield conn


def insert_file(conn: Connection, organization_id: uuid.UUID, name: str) -> uuid.UUID:
    file_id = uuid.uuid4()
    conn.execute(
        text(
            "INSERT INTO stored_files "
            "(id, organization_id, object_key, filename, content_type, size_bytes, sha256) "
            "VALUES (:id, :org, :key, :name, 'text/plain', 1, repeat('0', 64))"
        ),
        {
            "id": file_id,
            "org": organization_id,
            "key": f"tenants/{organization_id}/{file_id}",
            "name": name,
        },
    )
    return file_id
