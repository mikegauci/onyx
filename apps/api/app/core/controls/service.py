"""Read and change a workspace's pilot controls.

``feature_on`` is the one check automatic features call: it is false while manual mode is on,
whatever the feature's own switch says. It works for the app and the worker role (both are
bound to the tenant, and RLS scopes the row).
"""

import enum
import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.controls.models import WorkspaceControls
from app.core.errors import AppError, ErrorCode


class Feature(enum.StrEnum):
    ASSISTANT = "assistant"
    TEXT_BACK = "text_back"


FEATURE_COLUMN = {
    Feature.ASSISTANT: "assistant_enabled",
    Feature.TEXT_BACK: "text_back_enabled",
}


class FeaturePausedError(AppError):
    status_code = 409
    code = ErrorCode.FEATURE_PAUSED
    default_message = "This feature is paused for this workspace."


@dataclass(frozen=True)
class Controls:
    manual_mode: bool = False
    manual_mode_reason: str | None = None
    assistant_enabled: bool = True
    text_back_enabled: bool = True
    baseline_first_reply_minutes: int | None = None
    baseline_enquiries_per_week: int | None = None
    updated_by_user_id: uuid.UUID | None = None
    updated_at: datetime | None = None

    def feature_on(self, feature: Feature) -> bool:
        return not self.manual_mode and bool(getattr(self, FEATURE_COLUMN[feature]))


async def load_row(db: AsyncSession, organization_id: uuid.UUID) -> WorkspaceControls | None:
    return await db.scalar(
        select(WorkspaceControls).where(WorkspaceControls.organization_id == organization_id)
    )


async def load_controls(db: AsyncSession, organization_id: uuid.UUID) -> Controls:
    row = await load_row(db, organization_id)
    if row is None:
        return Controls()
    return Controls(
        manual_mode=row.manual_mode,
        manual_mode_reason=row.manual_mode_reason,
        assistant_enabled=row.assistant_enabled,
        text_back_enabled=row.text_back_enabled,
        baseline_first_reply_minutes=row.baseline_first_reply_minutes,
        baseline_enquiries_per_week=row.baseline_enquiries_per_week,
        updated_by_user_id=row.updated_by_user_id,
        updated_at=row.updated_at,
    )


async def feature_on(db: AsyncSession, organization_id: uuid.UUID, feature: Feature) -> bool:
    return (await load_controls(db, organization_id)).feature_on(feature)


async def ensure_feature_on(db: AsyncSession, organization_id: uuid.UUID, feature: Feature) -> None:
    controls = await load_controls(db, organization_id)
    if controls.manual_mode:
        raise FeaturePausedError(
            "Manual mode is on: Onyx is not drafting or sending anything automatically."
        )
    if not controls.feature_on(feature):
        raise FeaturePausedError(PAUSED_TEXT[feature])


PAUSED_TEXT = {
    Feature.ASSISTANT: "The assistant is paused for this workspace (Settings → Pilot controls).",
    Feature.TEXT_BACK: "Missed-call text-back is paused for this workspace.",
}
