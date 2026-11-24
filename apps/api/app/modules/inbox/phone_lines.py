"""Missed-call text-back settings (VA-004): what owners and admins may change on a phone line.

The number itself and its WhatsApp channel are set by a platform admin (they route webhooks).
Here the business chooses the approved utility template and its fixed values, the SMS
fallback text and sender name, the cooldown, and switches text-back on. A template must belong
to the line's WhatsApp channel, be usable, and render with the values given; turning text-back
on needs a template.
"""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit.record import record_workspace_audit
from app.core.auth.deps import WorkspaceAccess
from app.core.errors import ErrorDetail, NotFoundError, ValidationFailedError
from app.modules.inbox import schemas
from app.modules.inbox.channels.whatsapp import TemplateParamError, render_template
from app.modules.inbox.missed_calls import usable_template
from app.modules.inbox.models import (
    Channel,
    MissedCall,
    MissedCallOutcome,
    PhoneLine,
    WhatsAppTemplate,
)

STATS_WINDOW = timedelta(days=30)
SENT = (MissedCallOutcome.WHATSAPP_SENT, MissedCallOutcome.SMS_SENT)


def _invalid(field: str, message: str) -> ValidationFailedError:
    loc: list[str | int] = ["body", *(int(p) if p.isdigit() else p for p in field.split("."))]
    return ValidationFailedError(
        message, details=[ErrorDetail(loc=loc, msg=message, type="invalid")]
    )


class PhoneLineService:
    def __init__(self, db: AsyncSession, workspace: WorkspaceAccess) -> None:
        self.db = db
        self.workspace = workspace
        self.org = workspace.tenant.organization_id

    async def _out(self, line: PhoneLine) -> schemas.PhoneLineOut:
        channel = await self.db.scalar(
            select(Channel).where(
                Channel.organization_id == self.org, Channel.id == line.whatsapp_channel_id
            )
        )
        assert channel is not None  # noqa: S101 - same-tenant foreign key
        since = datetime.now(UTC) - STATS_WINDOW
        base = select(func.count(MissedCall.id)).where(
            MissedCall.organization_id == self.org,
            MissedCall.line_id == line.id,
            MissedCall.created_at >= since,
        )
        missed = await self.db.scalar(base) or 0
        sent = await self.db.scalar(base.where(MissedCall.outcome.in_(SENT))) or 0
        return schemas.PhoneLineOut(
            id=line.id,
            number=line.number,
            provider=line.provider,
            whatsapp_channel=schemas.ChannelRef(
                id=channel.id, kind=channel.kind, name=channel.name
            ),
            text_back_enabled=line.text_back_enabled,
            template_id=line.template_id,
            template_params=[str(p) for p in line.template_params],
            sms_text=line.sms_text,
            sms_sender=line.sms_sender,
            cooldown_hours=line.cooldown_hours,
            missed_calls_30d=missed,
            text_backs_30d=sent,
        )

    async def list(self) -> list[schemas.PhoneLineOut]:
        lines = (
            await self.db.scalars(
                select(PhoneLine)
                .where(PhoneLine.organization_id == self.org)
                .order_by(PhoneLine.created_at)
            )
        ).all()
        return [await self._out(line) for line in lines]

    async def _line(self, line_id: uuid.UUID) -> PhoneLine:
        line = await self.db.scalar(
            select(PhoneLine)
            .where(PhoneLine.organization_id == self.org, PhoneLine.id == line_id)
            .with_for_update()
        )
        if line is None:
            raise NotFoundError("Phone line not found.")
        return line

    async def update(
        self, line_id: uuid.UUID, body: schemas.PhoneLineUpdate
    ) -> schemas.PhoneLineOut:
        line = await self._line(line_id)
        values: dict[str, Any] = body.model_dump(exclude_unset=True)
        for field in ("text_back_enabled", "cooldown_hours", "template_params"):
            if field in values and values[field] is None:
                raise _invalid(field, "This field cannot be empty.")
        template_id = values.get("template_id", line.template_id)
        params = tuple(values.get("template_params", line.template_params))
        template: WhatsAppTemplate | None = None
        if template_id is not None:
            template = await self.db.scalar(
                select(WhatsAppTemplate).where(
                    WhatsAppTemplate.organization_id == self.org,
                    WhatsAppTemplate.channel_id == line.whatsapp_channel_id,
                    WhatsAppTemplate.id == template_id,
                )
            )
            if template is None:
                raise _invalid("template_id", "Template not found on this line's WhatsApp channel.")
            if not usable_template(template):
                raise _invalid(
                    "template_id", "Choose an approved utility template with body values only."
                )
            assert template.body is not None  # noqa: S101 - usable_template
            try:
                render_template(template.body, tuple(str(p) for p in params), template.param_count)
            except TemplateParamError as exc:
                loc = "template_params" if exc.index is None else f"template_params.{exc.index}"
                raise _invalid(loc, str(exc)) from exc
        enabled = values.get("text_back_enabled", line.text_back_enabled)
        if enabled and template is None:
            raise _invalid("template_id", "Choose a WhatsApp template before turning this on.")
        sms_text = values.get("sms_text", line.sms_text)
        sms_sender = values.get("sms_sender", line.sms_sender)
        if (sms_text is None) != (sms_sender is None):
            field = "sms_sender" if sms_sender is None else "sms_text"
            raise _invalid(field, "Set both the SMS text and the sender name, or neither.")

        changed = sorted(values)
        for field, value in values.items():
            setattr(line, field, list(value) if field == "template_params" else value)
        line.updated_at = datetime.now(UTC)
        await self.db.flush()
        await record_workspace_audit(
            self.db,
            self.workspace,
            action="inbox.phone_line.updated",
            target_type="phone_line",
            target_id=line.id,
            details={"fields": changed},
        )
        return await self._out(line)
