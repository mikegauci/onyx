"""Request transactions as the RLS-restricted application role.

Every request that touches the database runs in one transaction that first switches to the
``onyx_app`` role and sets ``app.current_auth_subject``, both transaction-locally, so nothing
leaks to the next user of a pooled connection.
"""

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

APP_ROLE = "onyx_app"


@asynccontextmanager
async def identity_transaction(
    sessions: async_sessionmaker[AsyncSession], auth_subject: uuid.UUID
) -> AsyncIterator[AsyncSession]:
    async with sessions() as session, session.begin():
        await session.execute(text(f"SET LOCAL ROLE {APP_ROLE}"))
        await session.execute(
            text("SELECT set_config('app.current_auth_subject', :subject, true)"),
            {"subject": str(auth_subject)},
        )
        yield session
