"""Keyset pagination over (timestamp, id), newest first. Cursors are opaque to clients."""

import base64
import uuid
from datetime import datetime

from sqlalchemy import Select, and_, or_
from sqlalchemy.orm import InstrumentedAttribute

from app.core.errors import AppError, ErrorCode


class InvalidCursorError(AppError):
    status_code = 400
    code = ErrorCode.BAD_REQUEST
    default_message = "Invalid cursor."


def encode_cursor(when: datetime, item_id: uuid.UUID) -> str:
    return base64.urlsafe_b64encode(f"{when.isoformat()}|{item_id}".encode()).decode()


def decode_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    try:
        when, item_id = base64.urlsafe_b64decode(cursor.encode()).decode().split("|")
        return datetime.fromisoformat(when), uuid.UUID(item_id)
    except (ValueError, UnicodeDecodeError) as exc:
        raise InvalidCursorError from exc


def paginate[*Ts](
    query: Select[*Ts],
    when: InstrumentedAttribute[datetime],
    item_id: InstrumentedAttribute[uuid.UUID],
    *,
    limit: int,
    cursor: str | None,
) -> Select[*Ts]:
    """Order newest first and fetch ``limit + 1`` rows (the extra row signals another page)."""
    query = query.order_by(when.desc(), item_id.desc()).limit(limit + 1)
    if cursor is not None:
        at, last_id = decode_cursor(cursor)
        query = query.where(or_(when < at, and_(when == at, item_id < last_id)))
    return query
