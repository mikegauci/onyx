"""Tenant settings checks shared by the workspace and platform-admin APIs.

The brand colour is shown behind white text (the workspace header and primary buttons), so it
must keep WCAG AA contrast with white: at least 4.5:1 for normal text.
"""

import re
from typing import Annotated, Literal
from zoneinfo import available_timezones

from pydantic import AfterValidator, StringConstraints

HEX = re.compile(r"^#[0-9a-f]{6}$")
MIN_CONTRAST_WITH_WHITE = 4.5
SLUG_PATTERN = r"^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$"

# EUR only for now: catalogue prices, VAT and quotes are euro throughout.
Currency = Literal["EUR"]


def _channel(value: int) -> float:
    c = value / 255
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def relative_luminance(color: str) -> float:
    r, g, b = (int(color[i : i + 2], 16) for i in (1, 3, 5))
    return 0.2126 * _channel(r) + 0.7152 * _channel(g) + 0.0722 * _channel(b)


def contrast_with_white(color: str) -> float:
    return 1.05 / (relative_luminance(color) + 0.05)


def check_brand_color(value: str) -> str:
    color = value.strip().lower()
    if not HEX.match(color):
        raise ValueError("Use a hex colour such as #1f4e79.")
    ratio = contrast_with_white(color)
    if ratio < MIN_CONTRAST_WITH_WHITE:
        raise ValueError(
            f"Too light for white text (contrast {ratio:.1f}:1, needs at least 4.5:1). "
            "Choose a darker colour."
        )
    return color


def check_timezone(value: str) -> str:
    if value not in _TIMEZONES:
        raise ValueError("Unknown IANA timezone.")
    return value


_TIMEZONES = frozenset(available_timezones())

BrandColor = Annotated[str, AfterValidator(check_brand_color)]
Timezone = Annotated[str, AfterValidator(check_timezone)]
OrgName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Slug = Annotated[str, StringConstraints(strip_whitespace=True, pattern=SLUG_PATTERN)]
