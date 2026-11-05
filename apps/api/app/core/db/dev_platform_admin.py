"""Local only: make a signed-in profile a platform admin.

Usage: ``python -m app.core.db.dev_platform_admin you@example.com``. Sign in once first so your
profile exists. Refuses in deployed environments; there, the owner grants it in SQL.
"""

import sys

from sqlalchemy import create_engine, select
from sqlalchemy.dialects.postgresql import insert

from app.core.admin.models import PlatformAdmin
from app.core.config import Settings
from app.core.db.seed import SeedRefusedError
from app.core.tenancy.models import User


def grant(settings: Settings, email: str) -> None:
    if settings.is_deployed:
        raise SeedRefusedError(f"Refusing to grant platform admin in {settings.environment!r}.")
    engine = create_engine(settings.require_migration_database_url())
    try:
        with engine.begin() as conn:
            user_id = conn.scalar(select(User.id).where(User.email == email))
            if user_id is None:
                raise SystemExit(f"No profile for {email}; sign in to the platform once first.")
            conn.execute(insert(PlatformAdmin).values(user_id=user_id).on_conflict_do_nothing())
    finally:
        engine.dispose()


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print(__doc__)
        return 2
    grant(Settings(), argv[0])
    print(f"{argv[0]} is now a platform admin.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
