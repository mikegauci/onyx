"""Imports every model module so ``Base.metadata`` is complete (Alembic, tests)."""

from app.ai import models as ai_models
from app.core.admin import models as admin_models
from app.core.audit import models as audit_models
from app.core.db.base import Base
from app.core.modules import models as module_models
from app.core.outbox import models as outbox_models
from app.core.storage import models as storage_models
from app.core.tenancy import models as tenancy_models
from app.modules.assistant import models as assistant_models
from app.modules.catalogue import models as catalogue_models
from app.modules.crm import models as crm_models
from app.modules.inbox import models as inbox_models
from app.modules.outbound import models as outbound_models
from app.modules.quotations import models as quotation_models

__all__ = [
    "Base",
    "admin_models",
    "ai_models",
    "assistant_models",
    "audit_models",
    "catalogue_models",
    "crm_models",
    "inbox_models",
    "module_models",
    "outbound_models",
    "outbox_models",
    "quotation_models",
    "storage_models",
    "tenancy_models",
]

# Tables that are shared reference or bookkeeping data rather than tenant- or user-owned.
# Every other table in the public schema must have row-level security enabled.
RLS_EXEMPT_TABLES = frozenset({"alembic_version", "modules"})

# Tables with an ``organization_id`` that keep their identity-scoped PR-004 policies (membership
# based, used before a workspace is selected). Every other table with ``organization_id`` must
# carry the standard tenant policies from ``app.core.db.rls``.
IDENTITY_SCOPED_TENANT_TABLES = frozenset(
    {"memberships", "invitations", "organization_modules", "audit_entries"}
)
