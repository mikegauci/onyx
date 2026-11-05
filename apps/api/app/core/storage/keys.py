"""Object keys for tenant files: always ``tenants/<organization_id>/<file_id>``.

Keys are built only on the server from the bound tenant and a server-generated file id; a
client-supplied name never becomes part of a key. Before any read or delete the key is checked
against the bound tenant again.
"""

import re
import uuid

TENANT_PREFIX = "tenants"

_UUID = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
OBJECT_KEY_PATTERN = re.compile(rf"{TENANT_PREFIX}/(?P<org>{_UUID})/(?P<file>{_UUID})")


class ObjectKeyError(ValueError):
    """The key is malformed or belongs to another tenant."""


def tenant_object_key(organization_id: uuid.UUID, file_id: uuid.UUID) -> str:
    return f"{TENANT_PREFIX}/{organization_id}/{file_id}"


def require_tenant_key(key: str, organization_id: uuid.UUID) -> str:
    """Return ``key`` if it is a well-formed key inside ``organization_id``'s prefix."""
    match = OBJECT_KEY_PATTERN.fullmatch(key)
    if match is None:
        raise ObjectKeyError("Malformed object key.")
    if match["org"] != str(organization_id):
        raise ObjectKeyError("Object key belongs to another tenant.")
    return key
