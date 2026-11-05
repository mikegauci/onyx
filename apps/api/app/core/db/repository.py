"""Base class for repositories over tenant-owned tables.

Row-level security already limits every query to the bound tenant. Repositories add a second,
explicit ``organization_id`` filter and set ``organization_id`` on insert from the bound
``TenantContext``, so callers can never choose the tenant through input.
"""

import uuid
from collections.abc import Sequence
from typing import Any, ClassVar, Protocol

from sqlalchemy import Select, delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped

from app.core.db.context import TenantContext


class TenantOwned(Protocol):
    id: Mapped[uuid.UUID]
    organization_id: Mapped[uuid.UUID]


class TenantScopeError(ValueError):
    """Raised when a caller tries to set ``organization_id`` itself."""


class TenantRepository[M: TenantOwned]:
    model: ClassVar[type[Any]]

    def __init__(self, session: AsyncSession, tenant: TenantContext) -> None:
        self._session = session
        self._tenant = tenant

    @property
    def tenant(self) -> TenantContext:
        return self._tenant

    def _select(self) -> Select[M]:
        return select(self.model).where(self.model.organization_id == self._tenant.organization_id)

    async def get(self, item_id: uuid.UUID) -> M | None:
        result: M | None = await self._session.scalar(
            self._select().where(self.model.id == item_id)
        )
        return result

    async def list(self) -> Sequence[M]:
        return (await self._session.scalars(self._select())).all()

    async def add(self, **values: Any) -> M:
        if "organization_id" in values:
            raise TenantScopeError("organization_id comes from the bound tenant, not input.")
        item: M = self.model(organization_id=self._tenant.organization_id, **values)
        self._session.add(item)
        await self._session.flush()
        return item

    async def delete(self, item_id: uuid.UUID) -> bool:
        result = await self._session.execute(
            delete(self.model).where(
                self.model.id == item_id,
                self.model.organization_id == self._tenant.organization_id,
            )
        )
        return bool(result.rowcount)  # type: ignore[attr-defined]
