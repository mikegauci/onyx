"""The module registry: which business modules exist and what each one requires.

The ``modules`` table is the catalogue in the database; this registry is the code's view of
it (a test keeps them identical). Entitlements, i.e. which modules a tenant may use, live in
``organization_modules`` and are checked on the server for every module request.
"""

import enum
from dataclasses import dataclass


class ModuleKey(enum.StrEnum):
    CRM = "crm"
    CATALOGUE = "catalogue"
    INBOX = "inbox"
    QUOTATIONS = "quotations"
    ORDERS = "orders"
    ASSISTANT = "assistant"
    OUTBOUND = "outbound"
    KNOWLEDGE = "knowledge"


@dataclass(frozen=True)
class ModuleSpec:
    key: ModuleKey
    name: str
    requires: frozenset[ModuleKey] = frozenset()


REGISTRY: dict[ModuleKey, ModuleSpec] = {
    spec.key: spec
    for spec in (
        ModuleSpec(ModuleKey.CRM, "CRM"),
        ModuleSpec(ModuleKey.CATALOGUE, "Product catalogue"),
        # Conversations link to CRM contacts and leads (PR-011).
        ModuleSpec(ModuleKey.INBOX, "Inbox", frozenset({ModuleKey.CRM})),
        ModuleSpec(
            ModuleKey.QUOTATIONS,
            "Quotations",
            frozenset({ModuleKey.CRM, ModuleKey.CATALOGUE}),
        ),
        ModuleSpec(ModuleKey.ORDERS, "Orders", frozenset({ModuleKey.QUOTATIONS})),
        # Reads inbox threads and the catalogue, and drafts quotes (PR-015).
        ModuleSpec(
            ModuleKey.ASSISTANT,
            "Sales assistant",
            frozenset({ModuleKey.INBOX, ModuleKey.CATALOGUE, ModuleKey.QUOTATIONS}),
        ),
        # Approves and sends replies on inbox conversations, with their quotes (PR-016).
        ModuleSpec(
            ModuleKey.OUTBOUND,
            "Outbound replies",
            frozenset({ModuleKey.INBOX, ModuleKey.QUOTATIONS}),
        ),
        # Tenant documents and policies, searched by staff and the assistant (PR-014).
        ModuleSpec(ModuleKey.KNOWLEDGE, "Knowledge"),
    )
}


def missing_requirements(key: ModuleKey, enabled: set[ModuleKey]) -> list[ModuleKey]:
    """Modules that must be enabled before ``key`` can be."""
    return sorted(REGISTRY[key].requires - enabled)


def enabled_dependents(key: ModuleKey, enabled: set[ModuleKey]) -> list[ModuleKey]:
    """Enabled modules that require ``key``, so it cannot be disabled while they are on."""
    return sorted(k for k in enabled if key in REGISTRY[k].requires)
