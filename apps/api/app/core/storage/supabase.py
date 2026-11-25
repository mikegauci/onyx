"""Supabase Storage backend: a private bucket, reached only with the server's service key.

Objects are never public: the dashboard and the customer upload page go through the API, which
checks the tenant and permission before reading a file. Keys are ``tenants/<org>/<file>``.
"""

import httpx

from app.core.storage.store import ObjectNotFoundError, _require_wellformed


class StorageError(RuntimeError):
    """The storage service refused or failed a request."""


class SupabaseObjectStore:
    def __init__(
        self, base_url: str, service_key: str, bucket: str, *, timeout: float = 30.0
    ) -> None:
        self._base = f"{base_url}/storage/v1/object/{bucket}"
        self._headers = {"Authorization": f"Bearer {service_key}", "apikey": service_key}
        self._timeout = timeout

    def _url(self, key: str) -> str:
        return f"{self._base}/{_require_wellformed(key)}"

    async def put(self, key: str, data: bytes, content_type: str) -> None:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(
                self._url(key),
                content=data,
                headers={**self._headers, "Content-Type": content_type, "x-upsert": "false"},
            )
        if response.status_code >= 300:
            raise StorageError(f"Storage upload failed ({response.status_code}).")

    async def get(self, key: str) -> bytes:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.get(self._url(key), headers=self._headers)
        if response.status_code in (400, 404):
            raise ObjectNotFoundError(key)
        if response.status_code >= 300:
            raise StorageError(f"Storage download failed ({response.status_code}).")
        return response.content

    async def delete(self, key: str) -> None:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.delete(self._url(key), headers=self._headers)
        if response.status_code >= 300 and response.status_code not in (400, 404):
            raise StorageError(f"Storage delete failed ({response.status_code}).")
