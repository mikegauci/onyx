"""Parsing and validating a contacts CSV. Pure functions: nothing here touches the database.

Format (UTF-8, optional BOM, comma-separated, first row is the header, names are
case-insensitive and may use spaces): ``full_name`` (required), ``email``, ``phone``,
``company``, ``notes``, ``lead_title``. Each row needs an email or a phone. Unknown columns are
ignored. A row with a ``lead_title`` also creates a lead.

Errors name the row (spreadsheet numbering: the header is row 1) and the column, never the
cell's value. Cells that look like spreadsheet formulas are stored as plain text; anything that
exports CSV later must escape them.
"""

import csv
import io
from dataclasses import dataclass, field

from app.modules.crm.identity import IdentityError, normalise_email, normalise_phone
from app.modules.crm.models import NOTE_MAX_LENGTH

MAX_BYTES = 1_000_000
MAX_ROWS = 2_000
COLUMNS = ("full_name", "email", "phone", "company", "notes", "lead_title")
_LIMITS = {"full_name": 200, "company": 200, "lead_title": 200, "notes": NOTE_MAX_LENGTH}


class ImportFileError(ValueError):
    """The file as a whole cannot be imported (size, header, CSV syntax)."""


@dataclass(frozen=True)
class RowError:
    row: int
    field: str
    message: str


@dataclass(frozen=True)
class ImportRow:
    row: int
    full_name: str
    email: str | None
    phone: str | None
    company: str | None
    notes: str | None
    lead_title: str | None


@dataclass
class ParsedImport:
    total: int = 0
    rows: list[ImportRow] = field(default_factory=list)
    errors: list[RowError] = field(default_factory=list)
    # (row, field, first row with the same value) for repeats inside the file.
    file_duplicates: list[tuple[int, str, int]] = field(default_factory=list)


def _header_key(name: str) -> str:
    return "_".join(name.strip().lower().replace("-", " ").split())


def parse_contacts_csv(content: str) -> ParsedImport:
    if len(content.encode("utf-8")) > MAX_BYTES:
        raise ImportFileError(f"The file is larger than {MAX_BYTES // 1_000_000} MB.")
    content = content.removeprefix("﻿")
    reader = csv.reader(io.StringIO(content, newline=""), strict=True)
    try:
        header = next(reader, None)
        if header is None:
            raise ImportFileError("The file is empty.")
        keys = [_header_key(h) for h in header]
        if "full_name" not in keys:
            raise ImportFileError("The header row must include a full_name column.")
        if "email" not in keys and "phone" not in keys:
            raise ImportFileError("The header row must include an email or a phone column.")
        repeated = sorted({k for k in keys if k in COLUMNS and keys.count(k) > 1})
        if repeated:
            raise ImportFileError(f"Repeated columns: {', '.join(repeated)}.")
        index = {k: i for i, k in enumerate(keys) if k in COLUMNS}

        result = ParsedImport()
        seen: dict[tuple[str, str], int] = {}
        for line_number, cells in enumerate(reader, start=2):
            if not any(c.strip() for c in cells):
                continue
            result.total += 1
            if result.total > MAX_ROWS:
                raise ImportFileError(f"The file has more than {MAX_ROWS} rows.")
            row = _parse_row(line_number, cells, index, result.errors)
            if row is None:
                continue
            duplicate = False
            for key in ("email", "phone"):
                value = getattr(row, key)
                if value is None:
                    continue
                first = seen.get((key, value))
                if first is not None:
                    result.file_duplicates.append((line_number, key, first))
                    duplicate = True
                    break
            if not duplicate:
                for key in ("email", "phone"):
                    value = getattr(row, key)
                    if value is not None:
                        seen[(key, value)] = line_number
                result.rows.append(row)
    except csv.Error as exc:
        raise ImportFileError(f"The file is not valid CSV (near row {reader.line_num}).") from exc
    return result


def _cell(cells: list[str], index: dict[str, int], key: str) -> str | None:
    position = index.get(key)
    if position is None or position >= len(cells):
        return None
    value = cells[position].strip()
    return value or None


def _parse_row(
    line: int, cells: list[str], index: dict[str, int], errors: list[RowError]
) -> ImportRow | None:
    values = {key: _cell(cells, index, key) for key in COLUMNS}
    row_errors: list[RowError] = []
    if values["full_name"] is None:
        row_errors.append(RowError(line, "full_name", "A name is required."))
    for key, limit in _LIMITS.items():
        value = values[key]
        if value is not None and len(value) > limit:
            row_errors.append(RowError(line, key, f"Must be at most {limit} characters."))
    email = phone = None
    try:
        email = normalise_email(values["email"])
    except IdentityError as exc:
        row_errors.append(RowError(line, "email", str(exc)))
    try:
        phone = normalise_phone(values["phone"])
    except IdentityError as exc:
        row_errors.append(RowError(line, "phone", str(exc)))
    if values["email"] is None and values["phone"] is None:
        row_errors.append(RowError(line, "email", "An email or a phone number is required."))
    if row_errors:
        errors.extend(row_errors)
        return None
    assert values["full_name"] is not None  # noqa: S101  # checked above
    return ImportRow(
        row=line,
        full_name=values["full_name"],
        email=email,
        phone=phone,
        company=values["company"],
        notes=values["notes"],
        lead_title=values["lead_title"],
    )
