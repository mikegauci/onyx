"""Object keys are built server-side and confined to the tenant's prefix."""

import uuid
from pathlib import Path

import pytest

from app.core.storage.keys import ObjectKeyError, require_tenant_key, tenant_object_key
from app.core.storage.store import LocalObjectStore

TENANT_A = uuid.UUID("00000000-0000-4000-8000-00000000000a")
TENANT_B = uuid.UUID("00000000-0000-4000-8000-00000000000b")
FILE = uuid.UUID("00000000-0000-4000-8000-0000000000f1")


def test_key_is_under_the_tenant_prefix() -> None:
    key = tenant_object_key(TENANT_A, FILE)
    assert key == f"tenants/{TENANT_A}/{FILE}"
    assert require_tenant_key(key, TENANT_A) == key


def test_key_of_another_tenant_is_rejected() -> None:
    with pytest.raises(ObjectKeyError, match="another tenant"):
        require_tenant_key(tenant_object_key(TENANT_B, FILE), TENANT_A)


@pytest.mark.parametrize(
    "key",
    [
        f"tenants/{TENANT_A}/../{TENANT_B}/{FILE}",
        f"tenants/{TENANT_A}/{FILE}/../../{TENANT_B}/{FILE}",
        f"/tenants/{TENANT_A}/{FILE}",
        f"tenants/{TENANT_A}/report.pdf",
        f"tenants/{TENANT_A}/{FILE}\n",
        f"TENANTS/{TENANT_A}/{FILE}",
        "",
    ],
)
def test_malformed_keys_are_rejected(key: str) -> None:
    with pytest.raises(ObjectKeyError):
        require_tenant_key(key, TENANT_A)


@pytest.mark.anyio
@pytest.mark.parametrize("anyio_backend", ["asyncio"])
async def test_local_store_stays_inside_its_root(tmp_path: Path, anyio_backend: str) -> None:
    store = LocalObjectStore(tmp_path)
    key = tenant_object_key(TENANT_A, FILE)
    await store.put(key, b"data", "text/plain")
    assert (tmp_path / key).read_bytes() == b"data"
    assert await store.get(key) == b"data"
    with pytest.raises(ObjectKeyError):
        await store.get(f"tenants/{TENANT_A}/../../etc/passwd")
