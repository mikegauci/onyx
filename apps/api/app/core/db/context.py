"""Transactions as the RLS-restricted roles, with identity and tenant bound transaction-locally.

- Requests: ``identity_transaction`` switches to ``onyx_app`` and sets
  ``app.current_auth_subject``; once membership is verified, ``bind_tenant`` sets
  ``app.current_organization_id``.
- Workers: ``worker_transaction`` switches to ``onyx_worker`` and binds the job's tenant.

Everything uses ``SET LOCAL`` / ``set_config(..., true)``, so it resets at commit or rollback
and nothing leaks to the next user of a pooled connection.
"""

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.db.rls import APP_ROLE, CURRENT_ORGANIZATION_SETTING, WORKER_ROLE

__all__ = [
    "APP_ROLE",
    "WORKER_ROLE",
    "TenantAccessDeniedError",
    "TenantContext",
    "bind_tenant",
    "identity_transaction",
    "worker_transaction",
]


class TenantAccessDeniedError(Exception):
    """The caller may not act for the requested organisation (or it does not exist)."""


@dataclass(frozen=True)
class TenantContext:
    """The organisation a transaction is bound to. Only the bind functions create one."""

    organization_id: uuid.UUID


async def _set_local(session: AsyncSession, setting: str, value: str) -> None:
    await session.execute(
        text("SELECT set_config(:setting, :value, true)"), {"setting": setting, "value": value}
    )


@asynccontextmanager
async def identity_transaction(
    sessions: async_sessionmaker[AsyncSession], auth_subject: uuid.UUID
) -> AsyncIterator[AsyncSession]:
    async with sessions() as session, session.begin():
        await session.execute(text(f"SET LOCAL ROLE {APP_ROLE}"))
        await _set_local(session, "app.current_auth_subject", str(auth_subject))
        yield session


async def bind_tenant(session: AsyncSession, organization_id: uuid.UUID) -> TenantContext:
    """Bind an identity transaction to ``organization_id`` if the caller is a member.

    The tenant id must come from a server-side membership lookup, never straight from a URL,
    body, header or model output. Membership is re-checked here and by every tenant policy.
    """
    await _set_local(session, CURRENT_ORGANIZATION_SETTING, str(organization_id))
    role = await session.scalar(text("SELECT app_membership_role(:org)"), {"org": organization_id})
    if role is None:
        raise TenantAccessDeniedError(str(organization_id))
    return TenantContext(organization_id=organization_id)


@asynccontextmanager
async def worker_transaction(
    sessions: async_sessionmaker[AsyncSession], organization_id: uuid.UUID
) -> AsyncIterator[tuple[AsyncSession, TenantContext]]:
    """A job transaction as ``onyx_worker``, bound to one existing organisation."""
    async with sessions() as session, session.begin():
        await session.execute(text(f"SET LOCAL ROLE {WORKER_ROLE}"))
        await _set_local(session, CURRENT_ORGANIZATION_SETTING, str(organization_id))
        found = await session.scalar(
            text("SELECT id FROM organizations WHERE id = :org"), {"org": organization_id}
        )
        if found is None:
            raise TenantAccessDeniedError(str(organization_id))
        yield session, TenantContext(organization_id=organization_id)
