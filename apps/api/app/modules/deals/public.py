"""The deals module's public interface for other modules (the sales assistant, VA-006)."""

import uuid
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth.deps import WorkspaceAccess
from app.core.modules.access import module_enabled
from app.core.modules.registry import ModuleKey
from app.modules.deals import schemas
from app.modules.deals.finance import DEFAULT_DISCLAIMER, FinanceService, load_settings, rates_of
from app.modules.deals.finance_rules import ApplicantType, Estimate, MaritalStatus, estimate


async def is_enabled(db: AsyncSession, workspace: WorkspaceAccess) -> bool:
    return await module_enabled(db, workspace, ModuleKey.DEALS)


@dataclass(frozen=True)
class FinanceEstimate:
    estimate: Estimate
    disclaimer: str


async def finance_estimate(
    db: AsyncSession, org: uuid.UUID, *, price_cents: int, deposit_cents: int, term_months: int
) -> FinanceEstimate:
    """The workspace's estimate. Raises ``EstimateError`` for inputs the rules refuse."""
    row = await load_settings(db, org)
    e = estimate(
        rates_of(row), price_cents=price_cents, deposit_cents=deposit_cents, term_months=term_months
    )
    return FinanceEstimate(e, row.disclaimer if row else DEFAULT_DISCLAIMER)


async def start_application(
    db: AsyncSession,
    workspace: WorkspaceAccess,
    *,
    contact_id: uuid.UUID,
    applicant_type: ApplicantType,
    marital_status: MaritalStatus,
    vehicle_label: str | None,
    price_cents: int | None,
    deposit_cents: int | None,
    term_months: int | None,
) -> uuid.UUID:
    """A finance application started by the assistant (no income details)."""
    detail = await FinanceService(db, workspace).create(
        schemas.FinanceApplicationCreate(
            contact_id=contact_id,
            applicant_type=applicant_type,
            marital_status=marital_status,
            vehicle_label=vehicle_label,
            price_cents=price_cents,
            deposit_cents=deposit_cents,
            term_months=term_months,
        ),
        source="assistant",
    )
    return detail.id


async def finance_disclaimer(db: AsyncSession, org: uuid.UUID) -> str:
    row = await load_settings(db, org)
    return row.disclaimer if row else DEFAULT_DISCLAIMER
