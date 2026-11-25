"""Deal stages, the pure rules for moving between them, and the standard document checklist.

```text
reserved → deposit_received → documents → finance → sold → collected
   └────────────── cancelled (any stage before sold) ──────────────┘
```

- Before ``sold``, a deal may move to any earlier or later open stage (staff fix mistakes);
  ``finance`` only when the deal is financed, ``deposit_received`` only with a deposit.
- ``sold`` needs every required document verified, unless an owner overrides with a reason.
- ``sold`` → ``collected`` only. ``collected`` and ``cancelled`` are final.

No database access here.
"""

import enum
from dataclasses import dataclass, field


class DealStage(enum.StrEnum):
    RESERVED = "reserved"
    DEPOSIT_RECEIVED = "deposit_received"
    DOCUMENTS = "documents"
    FINANCE = "finance"
    SOLD = "sold"
    COLLECTED = "collected"
    CANCELLED = "cancelled"


OPEN_STAGES = (
    DealStage.RESERVED,
    DealStage.DEPOSIT_RECEIVED,
    DealStage.DOCUMENTS,
    DealStage.FINANCE,
)
FINAL_STAGES = frozenset({DealStage.COLLECTED, DealStage.CANCELLED})
ACTIVE_STAGES = frozenset(OPEN_STAGES) | {DealStage.SOLD}  # the deal still holds its vehicle


class DealDocumentState(enum.StrEnum):
    MISSING = "missing"
    RECEIVED = "received"
    VERIFIED = "verified"
    REJECTED = "rejected"


class DealDepositMethod(enum.StrEnum):
    CASH = "cash"
    CARD = "card"
    BANK_TRANSFER = "bank_transfer"
    OTHER = "other"


class ChecklistCondition(enum.StrEnum):
    """When a checklist item applies to a deal."""

    ALWAYS = "always"
    FINANCED = "financed"
    TRADE_IN = "trade_in"
    DEPOSIT = "deposit"


@dataclass(frozen=True)
class ChecklistItem:
    key: str
    label: str
    required: bool = True
    note: str | None = None
    when: ChecklistCondition = ChecklistCondition.ALWAYS


STANDARD_CHECKLIST: tuple[ChecklistItem, ...] = (
    ChecklistItem("id_document", "ID card or passport", note="A clear photo of both sides."),
    ChecklistItem("driving_licence", "Driving licence", note="Both sides."),
    ChecklistItem(
        "proof_of_address",
        "Proof of address",
        note="A utility bill or bank statement from the last 3 months.",
    ),
    ChecklistItem("deposit_receipt", "Deposit receipt", when=ChecklistCondition.DEPOSIT),
    ChecklistItem(
        "finance_papers",
        "Finance papers",
        note="Payslips and the signed finance agreement.",
        when=ChecklistCondition.FINANCED,
    ),
    ChecklistItem(
        "trade_in_logbook",
        "Trade-in logbook",
        note="The registration document of the car you are trading in.",
        when=ChecklistCondition.TRADE_IN,
    ),
)


def applies(item: ChecklistItem, *, financed: bool, trade_in: bool, deposit: bool) -> bool:
    return {
        ChecklistCondition.ALWAYS: True,
        ChecklistCondition.FINANCED: financed,
        ChecklistCondition.TRADE_IN: trade_in,
        ChecklistCondition.DEPOSIT: deposit,
    }[item.when]


class StageRefusal(enum.StrEnum):
    FINAL = "final"
    SAME = "same"
    NOT_FINANCED = "not_financed"
    NO_DEPOSIT = "no_deposit"
    DOCUMENTS_INCOMPLETE = "documents_incomplete"
    NOT_SOLD = "not_sold"
    AFTER_SOLD = "after_sold"


REFUSAL_TEXT = {
    StageRefusal.FINAL: "This deal is closed and cannot change.",
    StageRefusal.SAME: "The deal is already at this stage.",
    StageRefusal.NOT_FINANCED: "Only a financed deal has a finance stage.",
    StageRefusal.NO_DEPOSIT: "Record the deposit first.",
    StageRefusal.DOCUMENTS_INCOMPLETE: (
        "Some required documents are not verified yet. An owner can mark it sold anyway, "
        "with a reason."
    ),
    StageRefusal.NOT_SOLD: "Mark the deal sold before it is collected.",
    StageRefusal.AFTER_SOLD: "A sold deal can only be marked collected.",
}


@dataclass(frozen=True)
class Move:
    allowed: bool
    refusal: StageRefusal | None = None
    overridden: bool = False  # sold despite unverified documents (owner override)
    missing: list[str] = field(default_factory=list)


def check_move(
    current: DealStage,
    target: DealStage,
    *,
    financed: bool,
    has_deposit: bool,
    unverified_required: list[str],
    override: bool,
) -> Move:
    if current in FINAL_STAGES:
        return Move(False, StageRefusal.FINAL)
    if current is target:
        return Move(False, StageRefusal.SAME)
    if current is DealStage.SOLD:
        if target is DealStage.COLLECTED:
            return Move(True)
        return Move(False, StageRefusal.AFTER_SOLD)
    if target is DealStage.COLLECTED:
        return Move(False, StageRefusal.NOT_SOLD)
    if target is DealStage.CANCELLED:
        return Move(True)
    if target is DealStage.FINANCE and not financed:
        return Move(False, StageRefusal.NOT_FINANCED)
    if target is DealStage.DEPOSIT_RECEIVED and not has_deposit:
        return Move(False, StageRefusal.NO_DEPOSIT)
    if target is DealStage.SOLD and unverified_required:
        if not override:
            return Move(False, StageRefusal.DOCUMENTS_INCOMPLETE, missing=unverified_required)
        return Move(True, overridden=True, missing=unverified_required)
    return Move(True)


# --- files ----------------------------------------------------------------------------------

MAX_FILE_BYTES = 10 * 1024 * 1024
_HEIF_BRANDS = (b"heic", b"heix", b"hevc", b"heim", b"heis", b"mif1", b"msf1")


def sniff(data: bytes) -> str | None:
    """The file's real type from its first bytes: PDF, JPEG, PNG or HEIC. None otherwise."""
    if data.startswith(b"%PDF-"):
        return "application/pdf"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if len(data) >= 12 and data[4:8] == b"ftyp" and data[8:12] in _HEIF_BRANDS:
        return "image/heic"
    return None
