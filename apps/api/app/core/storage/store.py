"""Object store backends. Callers go through ``TenantFileService``, never a store directly.

A Supabase Storage backend (private bucket, server-side service credentials) is added with the
first feature that stores real files; until then local development and tests use these.
"""

from pathlib import Path
from typing import Protocol

from app.core.storage.keys import OBJECT_KEY_PATTERN, ObjectKeyError


class ObjectNotFoundError(LookupError):
    pass


class ObjectStore(Protocol):
    async def put(self, key: str, data: bytes, content_type: str) -> None: ...
    async def get(self, key: str) -> bytes: ...
    async def delete(self, key: str) -> None: ...


def _require_wellformed(key: str) -> str:
    if OBJECT_KEY_PATTERN.fullmatch(key) is None:
        raise ObjectKeyError("Malformed object key.")
    return key


class InMemoryObjectStore:
    """For tests."""

    def __init__(self) -> None:
        self.objects: dict[str, tuple[bytes, str]] = {}

    async def put(self, key: str, data: bytes, content_type: str) -> None:
        self.objects[_require_wellformed(key)] = (data, content_type)

    async def get(self, key: str) -> bytes:
        try:
            return self.objects[_require_wellformed(key)][0]
        except KeyError as exc:
            raise ObjectNotFoundError(key) from exc

    async def delete(self, key: str) -> None:
        self.objects.pop(_require_wellformed(key), None)


class LocalObjectStore:
    """Files under ``root`` for local development. Paths never escape ``root``."""

    def __init__(self, root: Path) -> None:
        self._root = root.resolve()

    def _path(self, key: str) -> Path:
        path = (self._root / _require_wellformed(key)).resolve()
        if not path.is_relative_to(self._root):
            raise ObjectKeyError("Object key escapes the storage root.")
        return path

    async def put(self, key: str, data: bytes, content_type: str) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    async def get(self, key: str) -> bytes:
        try:
            return self._path(key).read_bytes()
        except FileNotFoundError as exc:
            raise ObjectNotFoundError(key) from exc

    async def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)
