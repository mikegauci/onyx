"""Application-layer tenant binding, repositories and file access across two tenants."""

import uuid
from collections.abc import AsyncIterator

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.db.context import (
    TenantAccessDeniedError,
    bind_tenant,
    identity_transaction,
    worker_transaction,
)
from app.core.db.repository import TenantScopeError
from app.core.db.seed import seed_auth_subject, seed_id
from app.core.storage.files import StoredFileNotFoundError, StoredFileRepository, TenantFileService
from app.core.storage.store import InMemoryObjectStore
from tests.rls_helpers import HARBOUR, LUMEN, OLIVIA, SAM

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
async def sessions(db_url: str) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    # One pooled connection, so consecutive transactions provably reuse it.
    engine = create_async_engine(db_url, pool_size=1, max_overflow=0)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


@pytest.fixture
def store() -> InMemoryObjectStore:
    return InMemoryObjectStore()


async def _upload(
    sessions: async_sessionmaker[AsyncSession],
    store: InMemoryObjectStore,
    email: str,
    org: uuid.UUID,
) -> uuid.UUID:
    async with identity_transaction(sessions, seed_auth_subject(email)) as db:
        tenant = await bind_tenant(db, org)
        stored = await TenantFileService(db, tenant, store).upload(
            filename="spec.pdf",
            content_type="application/pdf",
            data=b"%PDF lumen only",
            created_by_user_id=seed_id(email),
        )
        return stored.id


async def test_binding_a_tenant_without_membership_is_rejected(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    with pytest.raises(TenantAccessDeniedError):
        async with identity_transaction(sessions, seed_auth_subject(OLIVIA)) as db:
            await bind_tenant(db, HARBOUR)


async def test_binding_an_unknown_tenant_is_rejected(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    with pytest.raises(TenantAccessDeniedError):
        async with identity_transaction(sessions, seed_auth_subject(SAM)) as db:
            await bind_tenant(db, uuid.uuid4())


async def test_repository_refuses_a_caller_chosen_tenant(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    async with identity_transaction(sessions, seed_auth_subject(SAM)) as db:
        repository = StoredFileRepository(db, await bind_tenant(db, LUMEN))
        with pytest.raises(TenantScopeError):
            await repository.add(organization_id=HARBOUR, filename="x")


async def test_file_is_readable_in_its_own_tenant(
    sessions: async_sessionmaker[AsyncSession], store: InMemoryObjectStore
) -> None:
    file_id = await _upload(sessions, store, SAM, LUMEN)
    assert list(store.objects) == [f"tenants/{LUMEN}/{file_id}"]
    async with identity_transaction(sessions, seed_auth_subject(OLIVIA)) as db:
        content = await TenantFileService(db, await bind_tenant(db, LUMEN), store).read(file_id)
    assert content.data == b"%PDF lumen only"
    assert content.file.organization_id == LUMEN


async def test_another_tenants_file_looks_missing(
    sessions: async_sessionmaker[AsyncSession], store: InMemoryObjectStore
) -> None:
    file_id = await _upload(sessions, store, SAM, LUMEN)
    # Same user, other workspace: the Lumen file must be invisible from Harbour.
    async with identity_transaction(sessions, seed_auth_subject(SAM)) as db:
        tenant = await bind_tenant(db, HARBOUR)
        files = TenantFileService(db, tenant, store)
        with pytest.raises(StoredFileNotFoundError):
            await files.read(file_id)
        with pytest.raises(StoredFileNotFoundError):
            await files.delete(file_id)
        assert await StoredFileRepository(db, tenant).list() == []
    assert f"tenants/{LUMEN}/{file_id}" in store.objects


async def test_worker_access_is_limited_to_the_bound_tenant(
    sessions: async_sessionmaker[AsyncSession], store: InMemoryObjectStore
) -> None:
    file_id = await _upload(sessions, store, SAM, LUMEN)
    async with worker_transaction(sessions, HARBOUR) as (db, tenant):
        with pytest.raises(StoredFileNotFoundError):
            await TenantFileService(db, tenant, store).read(file_id)
    async with worker_transaction(sessions, LUMEN) as (db, tenant):
        content = await TenantFileService(db, tenant, store).read(file_id)
    assert content.data == b"%PDF lumen only"


async def test_worker_cannot_bind_an_unknown_tenant(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    with pytest.raises(TenantAccessDeniedError):
        async with worker_transaction(sessions, uuid.uuid4()):
            pass


async def test_pooled_connection_carries_no_context_into_the_next_transaction(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    async with identity_transaction(sessions, seed_auth_subject(SAM)) as db:
        await bind_tenant(db, LUMEN)
        first_pid = await db.scalar(text("SELECT pg_backend_pid()"))
    async with worker_transaction(sessions, HARBOUR) as (db, _):
        pass
    async with sessions() as db, db.begin():
        row = (
            await db.execute(
                text(
                    "SELECT pg_backend_pid(), current_user, "
                    "current_setting('app.current_auth_subject', true), "
                    "current_setting('app.current_organization_id', true)"
                )
            )
        ).one()
    pid, role, subject, org = row
    assert pid == first_pid
    assert role not in ("onyx_app", "onyx_worker")
    assert subject in ("", None)
    assert org in ("", None)
