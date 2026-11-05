"""Lead status lifecycle. The backend alone decides which transitions are allowed.

    new → contacted → qualified → won
    new | contacted | qualified → lost (needs a reason)
    lost → new (reopen)

``won`` is terminal for now; quotations (PR-012) attach to won and qualified leads.
"""

from app.modules.crm.models import LeadStatus

TRANSITIONS: dict[LeadStatus, frozenset[LeadStatus]] = {
    LeadStatus.NEW: frozenset({LeadStatus.CONTACTED, LeadStatus.LOST}),
    LeadStatus.CONTACTED: frozenset({LeadStatus.QUALIFIED, LeadStatus.LOST}),
    LeadStatus.QUALIFIED: frozenset({LeadStatus.WON, LeadStatus.LOST}),
    LeadStatus.WON: frozenset(),
    LeadStatus.LOST: frozenset({LeadStatus.NEW}),
}


def allowed_transitions(current: LeadStatus) -> list[LeadStatus]:
    return sorted(TRANSITIONS[current])


def can_transition(current: LeadStatus, target: LeadStatus) -> bool:
    return target in TRANSITIONS[current]
