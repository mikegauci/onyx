"""Imports every model module so ``Base.metadata`` is complete (Alembic, tests)."""

from app.core.audit import models as audit_models
from app.core.db.base import Base
from app.core.modules import models as module_models
from app.core.outbox import models as outbox_models
from app.core.tenancy import models as tenancy_models

__all__ = ["Base", "audit_models", "module_models", "outbox_models", "tenancy_models"]

# Tables that are shared reference or bookkeeping data rather than tenant- or user-owned.
# Every other table in the public schema must have row-level security enabled.
RLS_EXEMPT_TABLES = frozenset({"alembic_version", "modules"})
