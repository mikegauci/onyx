"""Customer upload links (VA-007 part 2): staff create them; customers upload with them.

A link's token is random (256 bits), shown to staff once, and stored only as its SHA-256. The
public endpoints resolve a token through ``deal_upload_link_lookup`` (SECURITY DEFINER, worker
only), then work in a worker transaction bound to that tenant. Every failure looks the same
("link not valid"), so a token cannot be probed. The public page sees only the business name
and the checklist items still needed: no names, deal details or uploaded files.
"""

import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.db.context import worker_transaction
from app.core.db.rls import WORKER_ROLE
from app.core.errors import NotFoundError, ValidationFailedError
from app.core.storage.files import TenantFileService
from app.core.storage.store import ObjectStore
from app.core.tasks.models import TaskAudience, TaskPriority
from app.core.tasks.service import open_task
from app.modules.deals.lifecycle import DealDocumentState, sniff
from app.modules.deals.models import Deal, DealDocument, DealEvent, DealUploadLink

LINK_LIFETIME = timedelta(days=7)
NEEDED = (DealDocumentState.MISSING, DealDocumentState.REJECTED)


class LinkNotValidError(NotFoundError):
    default_message = "This link is not valid any more. Ask the business for a new one."


def new_token() -> tuple[str, str]:
    token = secrets.token_urlsafe(32)
    return token, hash_token(token)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


async def active_link(
    db: AsyncSession, org: uuid.UUID, deal_id: uuid.UUID
) -> DealUploadLink | None:
    return await db.scalar(
        select(DealUploadLink)
        .where(
            DealUploadLink.organization_id == org,
            DealUploadLink.deal_id == deal_id,
            DealUploadLink.revoked_at.is_(None),
            DealUploadLink.expires_at > datetime.now(UTC),
        )
        .order_by(DealUploadLink.created_at.desc())
        .limit(1)
    )


async def revoke_links(db: AsyncSession, org: uuid.UUID, deal_id: uuid.UUID) -> int:
    result = await db.execute(
        update(DealUploadLink)
        .where(
            DealUploadLink.organization_id == org,
            DealUploadLink.deal_id == deal_id,
            DealUploadLink.revoked_at.is_(None),
        )
        .values(revoked_at=datetime.now(UTC))
    )
    return int(getattr(result, "rowcount", 0) or 0)


@dataclass(frozen=True)
class NeededItem:
    id: uuid.UUID
    form_kind: str | None
    label: str
    note: str | None
    rejected_reason: str | None


@dataclass(frozen=True)
class UploadPage:
    business_name: str
    expires_at: datetime
    needed: list[NeededItem]
    received: int  # items received or verified (shown as a count only)


@dataclass(frozen=True)
class _Resolved:
    organization_id: uuid.UUID
    deal_id: uuid.UUID
    link_id: uuid.UUID
    business_name: str


class CustomerUploads:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self.sessions = sessions

    async def _resolve(self, token: str) -> _Resolved:
        if not 20 <= len(token) <= 100:
            raise LinkNotValidError
        async with self.sessions() as session, session.begin():
            await session.execute(text(f"SET LOCAL ROLE {WORKER_ROLE}"))
            row = (
                await session.execute(
                    text("SELECT * FROM deal_upload_link_lookup(:hash)"),
                    {"hash": hash_token(token)},
                )
            ).first()
        if row is None:
            raise LinkNotValidError
        return _Resolved(row.organization_id, row.deal_id, row.link_id, row.business_name)

    async def page(self, token: str) -> UploadPage:
        link = await self._resolve(token)
        async with worker_transaction(self.sessions, link.organization_id) as (db, _tenant):
            return await self._page(db, link)

    async def _page(self, db: AsyncSession, link: _Resolved) -> UploadPage:
        expires = await db.scalar(
            select(DealUploadLink.expires_at).where(
                DealUploadLink.organization_id == link.organization_id,
                DealUploadLink.id == link.link_id,
            )
        )
        items = list(
            await db.scalars(
                select(DealDocument)
                .where(
                    DealDocument.organization_id == link.organization_id,
                    DealDocument.deal_id == link.deal_id,
                )
                .order_by(DealDocument.position, DealDocument.label)
            )
        )
        return UploadPage(
            business_name=link.business_name,
            expires_at=expires or datetime.now(UTC),
            needed=[
                NeededItem(
                    d.id,
                    d.form_kind,
                    d.label,
                    d.note,
                    d.rejection_reason if d.state is DealDocumentState.REJECTED else None,
                )
                for d in items
                if d.state in NEEDED
            ],
            received=sum(1 for d in items if d.state not in NEEDED),
        )

    async def upload(
        self,
        token: str,
        document_id: uuid.UUID,
        *,
        filename: str,
        data: bytes,
        store: ObjectStore,
    ) -> UploadPage:
        link = await self._resolve(token)
        content_type = sniff(data)
        if content_type is None:
            raise ValidationFailedError("Upload a photo (JPEG, PNG or HEIC) or a PDF.")
        async with worker_transaction(self.sessions, link.organization_id) as (db, tenant):
            item = await db.scalar(
                select(DealDocument)
                .where(
                    DealDocument.organization_id == link.organization_id,
                    DealDocument.deal_id == link.deal_id,
                    DealDocument.id == document_id,
                )
                .with_for_update()
            )
            if item is None or item.state not in NEEDED:
                raise LinkNotValidError("This document is not needed any more.")
            deal = await db.scalar(
                select(Deal).where(
                    Deal.organization_id == link.organization_id, Deal.id == link.deal_id
                )
            )
            files = TenantFileService(db, tenant, store)
            previous = item.file_id
            stored = await files.upload(
                filename=filename, content_type=content_type, data=data, created_by_user_id=None
            )
            now = datetime.now(UTC)
            item.file_id = stored.id
            item.state = DealDocumentState.RECEIVED
            item.rejection_reason = None
            item.received_at = now
            item.received_from = "customer"
            item.file_deleted_at = None
            await db.execute(
                update(DealUploadLink)
                .where(
                    DealUploadLink.organization_id == link.organization_id,
                    DealUploadLink.id == link.link_id,
                )
                .values(upload_count=DealUploadLink.upload_count + 1, last_used_at=now)
            )
            db.add(
                DealEvent(
                    organization_id=link.organization_id,
                    deal_id=link.deal_id,
                    kind="document_received",
                    details={"document": item.label, "source": "customer"},
                )
            )
            await db.flush()
            if previous is not None:
                await files.delete(previous)
            await open_task(
                db,
                tenant,
                kind="deal_document",
                title=f"Check {item.label.lower()} for {deal.title if deal else 'a deal'}",
                subject_type="deal",
                subject_id=link.deal_id,
                audience=TaskAudience.ADMIN,
                source_key=f"deal-document:{item.id}:{stored.id}",
                priority=TaskPriority.NORMAL,
            )
            return await self._page(db, link)

    async def form(self, token: str, kind: str, store: ObjectStore) -> tuple[str, bytes]:
        """A blank finance form (KYC or CCR) for a customer with a valid link."""
        from app.modules.deals.finance import load_settings

        link = await self._resolve(token)
        async with worker_transaction(self.sessions, link.organization_id) as (db, tenant):
            row = await load_settings(db, link.organization_id)
            file_id = getattr(row, f"{kind}_form_file_id", None) if row else None
            if file_id is None:
                raise LinkNotValidError("This form is not available.")
            content = await TenantFileService(db, tenant, store).read(file_id)
            return content.file.filename, content.data
