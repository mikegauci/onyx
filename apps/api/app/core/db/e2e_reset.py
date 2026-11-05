"""Local/CI only: rebuild the end-to-end test database from scratch and seed it.

Usage: ``python -m app.core.db.e2e_reset <database-url>``. The database name must end in
``_e2e`` and the host must be local, so this can never touch a shared or deployed database.
"""

import sys

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, make_url, text
from sqlalchemy.pool import NullPool

from app.core.db.seed import seed

LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}


class UnsafeTargetError(RuntimeError):
    pass


def reset(database_url: str) -> None:
    url = make_url(database_url)
    if not (url.database or "").endswith("_e2e") or url.host not in LOCAL_HOSTS:
        raise UnsafeTargetError("Refusing: e2e reset needs a local database named *_e2e.")
    admin = create_engine(
        url.set(database="postgres"), isolation_level="AUTOCOMMIT", poolclass=NullPool
    )
    try:
        with admin.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{url.database}" WITH (FORCE)'))
            conn.execute(text(f'CREATE DATABASE "{url.database}"'))
    finally:
        admin.dispose()

    config = Config("alembic.ini")
    config.attributes["database_url"] = url.render_as_string(hide_password=False)
    config.attributes["configure_logger"] = False
    command.upgrade(config, "head")
    engine = create_engine(url, poolclass=NullPool)
    try:
        with engine.begin() as conn:
            seed(conn)
    finally:
        engine.dispose()


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print(__doc__)
        return 2
    reset(argv[0])
    print(f"Reset e2e database {make_url(argv[0]).database}.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
