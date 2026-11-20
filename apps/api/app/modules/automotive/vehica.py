"""Reading car listings from a WordPress site running the Vehica theme (VA-001).

The site's REST API (``/wp-json/wp/v2/cars``) is public and read-only. Its data is untrusted:
every field is parsed, bounded and validated, and a field that cannot be read stays empty
rather than being guessed.

**SSRF guard.** The site's address is entered by staff, so the server only fetches ``https``
URLs whose host resolves to public addresses, never follows redirects, and caps every
response's size.
"""

import asyncio
import html
import ipaddress
import json
import re
import socket
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import urlparse

import httpx

from app.modules.automotive.models import VehicleStatus

PAGE_SIZE = 100
MAX_PAGES = 50  # 5,000 listings
MAX_RESPONSE_BYTES = 5 * 1024 * 1024
MAX_PHOTOS = 30
TIMEOUT_SECONDS = 20.0

Resolver = Callable[[str], Awaitable[list[str]]]


class SourceError(Exception):
    """The site could not be read. ``code`` is safe to show and log."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


async def _resolve(host: str) -> list[str]:
    infos = await asyncio.get_running_loop().getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    return [str(info[4][0]) for info in infos]


async def safe_base_url(url: str, resolve: Resolver = _resolve) -> str:
    """The site's base URL if it is https on a public host; otherwise ``SourceError``."""
    parsed = urlparse(url.strip())
    host = parsed.hostname
    if parsed.scheme != "https" or not host or parsed.username or parsed.password:
        raise SourceError("must_be_https")
    if parsed.port not in (None, 443):
        raise SourceError("port_not_allowed")
    try:
        addresses = await resolve(host)
    except OSError as exc:
        raise SourceError("host_not_found") from exc
    if not addresses:
        raise SourceError("host_not_found")
    for address in addresses:
        ip = ipaddress.ip_address(address)
        if not ip.is_global:
            raise SourceError("host_not_public")
    return f"https://{host}{parsed.path.rstrip('/')}"


class VehicaClient:
    def __init__(
        self,
        base_url: str,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout: float = TIMEOUT_SECONDS,
    ) -> None:
        self._base = base_url.rstrip("/")
        self._client = httpx.AsyncClient(
            timeout=timeout,
            transport=transport,
            follow_redirects=False,
            headers={"User-Agent": "Onyx listing import", "Accept": "application/json"},
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _get(self, path: str, params: dict[str, str | int]) -> tuple[Any, httpx.Headers]:
        try:
            async with self._client.stream("GET", f"{self._base}{path}", params=params) as r:
                if r.status_code in (301, 302, 303, 307, 308):
                    raise SourceError("redirect_not_followed")
                if r.status_code == 404:
                    raise SourceError("not_a_vehica_site")
                if r.status_code >= 400:
                    raise SourceError(f"http_{r.status_code}")
                body = b""
                async for chunk in r.aiter_bytes():
                    body += chunk
                    if len(body) > MAX_RESPONSE_BYTES:
                        raise SourceError("response_too_large")
                headers = r.headers
        except httpx.TimeoutException as exc:
            raise SourceError("timeout") from exc
        except httpx.HTTPError as exc:
            raise SourceError("unreachable") from exc
        try:
            return json.loads(body), headers
        except ValueError as exc:
            raise SourceError("not_json") from exc

    async def listings(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        page, pages = 1, 1
        while page <= min(pages, MAX_PAGES):
            data, headers = await self._get(
                "/wp-json/wp/v2/cars", {"per_page": PAGE_SIZE, "page": page}
            )
            if not isinstance(data, list):
                raise SourceError("not_a_vehica_site")
            out.extend(item for item in data if isinstance(item, dict))
            total = headers.get("x-wp-totalpages", "1")
            pages = int(total) if total.isdigit() else 1
            page += 1
        return out

    async def terms(self, taxonomy: str, ids: Sequence[int]) -> dict[int, str]:
        """Term names by id for one taxonomy (only the ids used by the listings)."""
        names: dict[int, str] = {}
        unique = sorted(set(ids))
        for start in range(0, len(unique), PAGE_SIZE):
            chunk = unique[start : start + PAGE_SIZE]
            data, _ = await self._get(
                f"/wp-json/wp/v2/{taxonomy}",
                {"include": ",".join(map(str, chunk)), "per_page": PAGE_SIZE},
            )
            for term in data if isinstance(data, list) else []:
                if isinstance(term, dict) and isinstance(term.get("id"), int):
                    names[term["id"]] = _text(term.get("name"), 100) or ""
        return names


# --- the field map ---------------------------------------------------------------------------

# Which Vehica field holds what on Ventur's site (read from its public API, 20 November 2026).
# Each tenant's map is stored with its source and can be edited; "status" is not mapped yet.
DEFAULT_FIELD_MAP: dict[str, dict[str, str]] = {
    "make": {"field": "vehica_6659", "kind": "term"},
    "model": {"field": "vehica_6660", "kind": "term"},
    "condition": {"field": "vehica_6654", "kind": "term"},
    "body_type": {"field": "vehica_6655", "kind": "term"},
    "transmission": {"field": "vehica_6662", "kind": "term"},
    "fuel": {"field": "vehica_6663", "kind": "term"},
    "colour": {"field": "vehica_6666", "kind": "term"},
    "doors": {"field": "vehica_12770", "kind": "term_number"},
    "features": {"field": "vehica_6670", "kind": "terms"},
    "year": {"field": "vehica_14696", "kind": "number"},
    "mileage_km": {"field": "vehica_6664", "kind": "number"},
    "engine_cc": {"field": "vehica_6665", "kind": "number"},
    "stock_number": {"field": "vehica_6671", "kind": "text"},
    "price_cents": {"field": "vehica_6656", "kind": "price"},
    "photos": {"field": "vehica_6673", "kind": "urls"},
    "video_url": {"field": "vehica_6674", "kind": "video"},
}
KINDS = frozenset({"term", "terms", "term_number", "number", "text", "price", "urls", "video"})
# The optional "sold"/"reserved" rule: {"field": "vehica_6657", "values": ["Sold"]}
STATUS_RULES = ("sold", "reserved")


def term_taxonomies(field_map: dict[str, Any]) -> list[str]:
    return sorted(
        {
            spec["field"]
            for spec in field_map.values()
            if isinstance(spec, dict) and spec.get("kind") in ("term", "terms", "term_number")
        }
        | {
            rule["field"]
            for key, rule in field_map.items()
            if key in STATUS_RULES and isinstance(rule, dict) and rule.get("field")
        }
    )


@dataclass(frozen=True)
class ParsedVehicle:
    source_ref: str
    title: str
    listing_url: str | None
    modified_at: datetime | None
    status: VehicleStatus
    fields: dict[str, Any] = field(default_factory=dict)
    # Where each field came from: {"mileage_km": "vehica_6664"}
    origins: dict[str, str] = field(default_factory=dict)


_SPACE = re.compile(r"\s+")
_DIGITS = re.compile(r"\d+")


def _text(value: Any, limit: int) -> str | None:
    if not isinstance(value, str | int | float) or isinstance(value, bool):
        return None
    text = _SPACE.sub(" ", html.unescape(str(value))).strip()
    return text[:limit] if text else None


def _number(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str):
        cleaned = value.replace(",", "").replace(" ", "").strip()
        return int(cleaned) if cleaned.isdigit() else None
    return None


def _cents(value: Any) -> int | None:
    """A Vehica price ``{"vehica_currency_…": "12500"}`` (or a bare amount) in cents."""
    raw = next(iter(value.values()), None) if isinstance(value, dict) else value
    text = _text(raw, 32)
    if text is None:
        return None
    try:
        amount = Decimal(text.replace(",", "").replace("€", "").strip())
    except InvalidOperation:
        return None
    if amount < 0 or amount > Decimal("100000000"):
        return None
    return int((amount * 100).to_integral_value())


def _https(value: Any) -> str | None:
    text = _text(value, 1000)
    return text if text and urlparse(text).scheme == "https" else None


def _terms(value: Any, names: dict[int, str]) -> list[str]:
    ids = value if isinstance(value, list) else []
    return [names[i] for i in ids if isinstance(i, int) and names.get(i)]


def _read(kind: str, value: Any, names: dict[int, str]) -> Any:
    if kind == "term":
        found = _terms(value, names)
        return found[0] if found else None
    if kind == "terms":
        return _terms(value, names)[:100]
    if kind == "term_number":
        found = _terms(value, names)
        digits = _DIGITS.search(found[0]) if found else None
        return int(digits.group()) if digits else None
    if kind == "number":
        return _number(value)
    if kind == "text":
        return _text(value, 64)
    if kind == "price":
        return _cents(value)
    if kind == "urls":
        urls = [u for u in (_https(v) for v in (value if isinstance(value, list) else [])) if u]
        return urls[:MAX_PHOTOS]
    if kind == "video":
        return _https(value.get("url")) if isinstance(value, dict) else _https(value)
    return None


def _valid(name: str, value: Any) -> Any:
    if name == "year" and value is not None and not 1900 <= value <= 2100:
        return None
    if name in ("mileage_km", "engine_cc", "doors") and value is not None and value < 0:
        return None
    return value


def _status(
    raw: dict[str, Any], field_map: dict[str, Any], names: dict[str, dict[int, str]]
) -> VehicleStatus:
    for key in STATUS_RULES:
        rule = field_map.get(key)
        if not isinstance(rule, dict) or not rule.get("field"):
            continue
        values = {str(v).casefold() for v in rule.get("values", [])}
        found = {t.casefold() for t in _terms(raw.get(rule["field"]), names.get(rule["field"], {}))}
        if values & found:
            return VehicleStatus(key)
    return VehicleStatus.AVAILABLE


def parse_listing(
    raw: dict[str, Any], field_map: dict[str, Any], names: dict[str, dict[int, str]]
) -> ParsedVehicle | None:
    """One Vehica listing as vehicle fields, or None when it is not a usable listing."""
    post_id = raw.get("id")
    title = _text((raw.get("title") or {}).get("rendered"), 300)
    if not isinstance(post_id, int) or not title or raw.get("status") not in (None, "publish"):
        return None
    fields: dict[str, Any] = {}
    origins: dict[str, str] = {}
    for name, spec in field_map.items():
        if name in STATUS_RULES or not isinstance(spec, dict):
            continue
        source, kind = spec.get("field"), spec.get("kind")
        if not isinstance(source, str) or kind not in KINDS:
            continue
        value = _valid(name, _read(kind, raw.get(source), names.get(source, {})))
        if value is None or value == []:
            continue
        fields[name] = value
        origins[name] = source
    modified = _text(raw.get("modified_gmt"), 40)
    try:
        modified_at = datetime.fromisoformat(modified).replace(tzinfo=UTC) if modified else None
    except ValueError:
        modified_at = None
    return ParsedVehicle(
        source_ref=f"wp:{post_id}",
        title=title,
        listing_url=_https(raw.get("link")),
        modified_at=modified_at,
        status=_status(raw, field_map, names),
        fields=fields,
        origins=origins,
    )


def term_ids(listings: Sequence[dict[str, Any]], taxonomy: str) -> list[int]:
    ids: list[int] = []
    for raw in listings:
        value = raw.get(taxonomy)
        if isinstance(value, list):
            ids.extend(i for i in value if isinstance(i, int))
    return ids
