"""Contact identity: normalised email and phone, the keys used for deduplication.

Normalisation is deliberately simple and deterministic (no external dependency):

- email: trimmed and lower-cased (the column is ``citext`` as well);
- phone: spaces, dots, dashes and brackets removed; a leading ``00`` becomes ``+``; a bare
  8-digit number is treated as Maltese and gets ``+356``. The result must be ``+`` followed by
  8 to 15 digits (E.164 length). Other national formats must be entered with their country code.
"""

import re

from email_validator import EmailNotValidError, validate_email

DEFAULT_COUNTRY_CODE = "356"  # Malta; the first tenants are Maltese (tenant setting later)
_PHONE_SEPARATORS = re.compile(r"[\s.\-()/]")
_E164 = re.compile(r"\+[1-9]\d{7,14}")
_NATIONAL_DIGITS = 8


class IdentityError(ValueError):
    """An email or phone number that cannot be normalised. The message never echoes it."""


def normalise_email(value: str | None) -> str | None:
    if value is None or not value.strip():
        return None
    try:
        # Syntax only (no DNS); test_environment admits the reserved .test domain (fixtures).
        result = validate_email(value.strip(), check_deliverability=False, test_environment=True)
    except EmailNotValidError as exc:
        raise IdentityError("Enter a valid email address.") from exc
    return result.normalized.lower()


def normalise_phone(value: str | None) -> str | None:
    if value is None or not value.strip():
        return None
    compact = _PHONE_SEPARATORS.sub("", value.strip())
    if compact.startswith("00"):
        compact = "+" + compact[2:]
    if compact.isdigit() and len(compact) == _NATIONAL_DIGITS:
        compact = f"+{DEFAULT_COUNTRY_CODE}{compact}"
    if not _E164.fullmatch(compact):
        raise IdentityError("Enter a phone number with its country code, e.g. +356 2123 4567.")
    return compact
