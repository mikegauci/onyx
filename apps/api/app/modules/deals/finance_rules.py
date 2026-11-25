"""Finance estimate and checklists (VA-006). Pure functions, exact decimals, no database.

The estimate is the formula Ventur publishes on ventur.com.mt/loan-calculator (simple interest):

    net loan   = price - deposit
    interest   = net x annual rate x years
    yearly fee = net x yearly fee rate x years   ("financing & maintenance fee")
    onboarding = net x onboarding fee rate
    total      = net + interest + yearly fee + onboarding
    monthly    = total / months

Rates are basis points (650 = 6.5%). Amounts are integer cents; results are rounded half up
to the cent only at the end, so the figures match the website's.
"""

import enum
import re
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

STANDARD_RATES = {"annual_rate_bp": 650, "onboarding_fee_bp": 400, "yearly_fee_bp": 100}
CENT = Decimal("1")


class ApplicantType(enum.StrEnum):
    MALTESE_RESIDENT = "maltese_resident"
    NON_MALTESE_RESIDENT = "non_maltese_resident"
    SELF_EMPLOYED = "self_employed"
    COMPANY = "company"


class MaritalStatus(enum.StrEnum):
    SINGLE = "single"
    MARRIED = "married"
    SEPARATED = "separated"
    DIVORCED = "divorced"
    WIDOWED = "widowed"
    NOT_APPLICABLE = "not_applicable"


class ApplicationStatus(enum.StrEnum):
    STARTED = "started"
    DOCUMENTS = "documents"
    IN_REVIEW = "in_review"  # with Ventur's finance team
    APPROVED = "approved"
    DECLINED = "declined"
    WITHDRAWN = "withdrawn"


DECIDED = frozenset({ApplicationStatus.APPROVED, ApplicationStatus.DECLINED})
CLOSED = DECIDED | {ApplicationStatus.WITHDRAWN}


class EstimateError(ValueError):
    pass


@dataclass(frozen=True)
class Rates:
    annual_rate_bp: int
    onboarding_fee_bp: int
    yearly_fee_bp: int
    min_term_months: int = 6
    max_term_months: int = 120


@dataclass(frozen=True)
class Estimate:
    price_cents: int
    deposit_cents: int
    term_months: int
    net_loan_cents: int
    interest_cents: int
    yearly_fee_cents: int
    onboarding_fee_cents: int
    total_cents: int
    monthly_cents: int
    annual_rate_bp: int
    payoff_months: int | None = None
    payoff_saving_cents: int | None = None


def _bp(value: int) -> Decimal:
    return Decimal(value) / Decimal(10_000)


def _cents(value: Decimal) -> int:
    return int(value.quantize(CENT, rounding=ROUND_HALF_UP))


def estimate(
    rates: Rates,
    *,
    price_cents: int,
    deposit_cents: int,
    term_months: int,
    payoff_months: int | None = None,
) -> Estimate:
    if price_cents <= 0:
        raise EstimateError("The vehicle price must be more than zero.")
    if deposit_cents < 0:
        raise EstimateError("The deposit cannot be negative.")
    if deposit_cents >= price_cents:
        raise EstimateError("The deposit must be less than the price.")
    if not rates.min_term_months <= term_months <= rates.max_term_months:
        raise EstimateError(
            f"Choose a term between {rates.min_term_months} and {rates.max_term_months} months."
        )
    if term_months % 6:
        raise EstimateError("The term goes in half years (6, 12, 18 … months).")
    net = Decimal(price_cents - deposit_cents)
    years = Decimal(term_months) / Decimal(12)
    interest = net * _bp(rates.annual_rate_bp) * years
    yearly_fee = net * _bp(rates.yearly_fee_bp) * years
    onboarding = net * _bp(rates.onboarding_fee_bp)
    total = net + interest + yearly_fee + onboarding
    saving: int | None = None
    if payoff_months is not None:
        if not 0 < payoff_months < term_months:
            raise EstimateError("Pay off early must be shorter than the term.")
        early_years = Decimal(payoff_months) / Decimal(12)
        early = net * (_bp(rates.annual_rate_bp) + _bp(rates.yearly_fee_bp)) * early_years
        saving = _cents(max(interest + yearly_fee - early, Decimal(0)))
    return Estimate(
        price_cents=price_cents,
        deposit_cents=deposit_cents,
        term_months=term_months,
        net_loan_cents=int(net),
        interest_cents=_cents(interest),
        yearly_fee_cents=_cents(yearly_fee),
        onboarding_fee_cents=_cents(onboarding),
        total_cents=_cents(total),
        monthly_cents=_cents(total / Decimal(term_months)),
        annual_rate_bp=rates.annual_rate_bp,
        payoff_months=payoff_months,
        payoff_saving_cents=saving,
    )


# --- checklists (ventur.com.mt/loan-calculator, 2026-11-25) ---------------------------------

KYC = "Completed KYC & Loan Request Form"
CCR = "Signed CCR Form"

STANDARD_CHECKLISTS: dict[str, dict[str, list[str]]] = {
    ApplicantType.MALTESE_RESIDENT: {
        "base": ["ID Card", "Vehicle Licence", "Last 3 months payslips", "Latest FS3", KYC, CCR],
        "spouse": [
            "Spouse ID Card",
            "Spouse last 3 months payslips",
            "Spouse latest FS3",
            "Spouse signature on the KYC & Loan Request Form",
            "Spouse signature on the CCR Form",
        ],
    },
    ApplicantType.NON_MALTESE_RESIDENT: {
        "base": [
            "ID Card / Residence Card",
            "Vehicle Licence",
            "Passport",
            "Last 3 months payslips",
            "Latest FS3",
            "Work Contract",
            "JobsPlus History",
            "Rental Agreement (if applicable)",
            KYC,
            CCR,
        ],
        "spouse": [
            "Spouse ID Card / Residence Card",
            "Spouse Passport",
            "Spouse last 3 months payslips",
            "Spouse latest FS3",
            "Spouse Work Contract",
            "Spouse JobsPlus History",
            "Spouse signature on the KYC & Loan Request Form",
            "Spouse signature on the CCR Form",
        ],
    },
    ApplicantType.SELF_EMPLOYED: {
        "base": [
            "ID Card",
            "Vehicle Licence",
            "Passport (if not a Maltese resident)",
            "Last 2 years P&L signed and stamped by an accountant",
            "Last 2 years Income Tax Return signed and stamped by an accountant",
            "Rental Agreement (if applicable)",
            KYC,
            CCR,
        ],
        "spouse": [
            "Spouse ID Card",
            "Spouse employment or self-employed documents",
            "Spouse signature on the KYC & Loan Request Form",
            "Spouse signature on the CCR Form",
        ],
    },
    ApplicantType.COMPANY: {
        "base": [
            "Audited or management accounts for the last 2 years, signed by an accountant",
            "Memorandum and Articles",
            "Certificate of Incorporation",
            "Board Resolution authorising the signatories",
            "ID and proof of address of all shareholders",
            "Last 3 payslips of the surety",
            "Latest FS3 of the surety",
            "Certificate of Beneficial Owners (Malta Business Registry)",
            KYC,
            CCR,
        ],
        "spouse": [],
    },
}

OPTIONAL_HINT = re.compile(r"\((if applicable|if not a Maltese resident)\)", re.IGNORECASE)


@dataclass(frozen=True)
class FinanceItem:
    key: str
    label: str
    required: bool
    form_kind: str | None


def _key(label: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_")[:33]
    return f"fin_{slug}"


def checklist_for(
    applicant: ApplicantType,
    marital: MaritalStatus,
    overrides: dict[str, dict[str, list[str]]] | None = None,
) -> list[FinanceItem]:
    """The documents a financed deal needs for this applicant (spouse items when married)."""
    lists = (overrides or {}).get(applicant.value) or STANDARD_CHECKLISTS[applicant]
    labels = list(lists.get("base", []))
    if marital is MaritalStatus.MARRIED:
        labels += lists.get("spouse", [])
    items: list[FinanceItem] = []
    seen: set[str] = set()
    for label in labels:
        key = _key(label)
        if key in seen:
            continue
        seen.add(key)
        form = "kyc" if label == KYC else "ccr" if label == CCR else None
        items.append(FinanceItem(key, label[:100], not OPTIONAL_HINT.search(label), form))
    return items
