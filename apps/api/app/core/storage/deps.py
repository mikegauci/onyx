"""The tenant file store for a request (deal documents). 503 when storage is not set up."""

from pathlib import Path
from typing import Annotated

from fastapi import Depends, Request

from app.core.config import Settings
from app.core.errors import ServiceUnavailableError
from app.core.storage.store import InMemoryObjectStore, LocalObjectStore, ObjectStore
from app.core.storage.supabase import SupabaseObjectStore


def build_object_store(settings: Settings) -> ObjectStore | None:
    backend = settings.resolved_storage_backend
    if backend == "memory":
        return InMemoryObjectStore()
    if backend == "local":
        return LocalObjectStore(Path(settings.storage_local_dir))
    if backend == "supabase" and settings.supabase_url and settings.supabase_service_key:
        return SupabaseObjectStore(
            settings.supabase_url,
            settings.supabase_service_key.get_secret_value(),
            settings.storage_bucket,
        )
    return None


def get_object_store(request: Request) -> ObjectStore:
    store: ObjectStore | None = getattr(request.app.state, "object_store", None)
    if store is None:
        raise ServiceUnavailableError("File storage is not set up on this server yet.")
    return store


ObjectStoreDep = Annotated[ObjectStore, Depends(get_object_store)]
