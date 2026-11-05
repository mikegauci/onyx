"""Tenant file access: metadata through RLS, bytes from the tenant's storage prefix.

A file is reachable only if its metadata row is visible in the bound tenant (row-level
security plus an explicit filter) and its key is inside that tenant's prefix. Another tenant's
file id therefore behaves exactly like a missing one.

Upload writes the object after the row is flushed; if the transaction later rolls back the
object is orphaned (never exposed, since no row points at it). Reconciliation of orphaned
objects is a follow-up for the first feature that stores real files.
"""

import hashlib
import uuid
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.context import TenantContext
from app.core.db.repository import TenantRepository
from app.core.storage.keys import require_tenant_key, tenant_object_key
from app.core.storage.models import StoredFile
from app.core.storage.store import ObjectStore


class StoredFileNotFoundError(LookupError):
    """No such file in the bound tenant (it may exist in another one)."""


class StoredFileRepository(TenantRepository[StoredFile]):
    model = StoredFile


@dataclass(frozen=True)
class FileContent:
    file: StoredFile
    data: bytes


class TenantFileService:
    def __init__(self, session: AsyncSession, tenant: TenantContext, store: ObjectStore) -> None:
        self._files = StoredFileRepository(session, tenant)
        self._tenant = tenant
        self._store = store

    async def upload(
        self,
        *,
        filename: str,
        content_type: str,
        data: bytes,
        created_by_user_id: uuid.UUID | None,
    ) -> StoredFile:
        file_id = uuid.uuid4()
        stored = await self._files.add(
            id=file_id,
            object_key=tenant_object_key(self._tenant.organization_id, file_id),
            filename=filename,
            content_type=content_type,
            size_bytes=len(data),
            sha256=hashlib.sha256(data).hexdigest(),
            created_by_user_id=created_by_user_id,
        )
        await self._store.put(stored.object_key, data, content_type)
        return stored

    async def read(self, file_id: uuid.UUID) -> FileContent:
        stored = await self._get(file_id)
        data = await self._store.get(
            require_tenant_key(stored.object_key, self._tenant.organization_id)
        )
        return FileContent(file=stored, data=data)

    async def delete(self, file_id: uuid.UUID) -> None:
        stored = await self._get(file_id)
        key = require_tenant_key(stored.object_key, self._tenant.organization_id)
        await self._files.delete(file_id)
        await self._store.delete(key)

    async def _get(self, file_id: uuid.UUID) -> StoredFile:
        stored = await self._files.get(file_id)
        if stored is None:
            raise StoredFileNotFoundError(str(file_id))
        return stored
