from __future__ import annotations

from urllib.parse import urlparse

import phonenumbers

from .models import Business


def normalize_domain(url: str | None) -> str | None:
    if not url:
        return None
    u = url.strip().lower()
    host = urlparse(u if "://" in u else f"//{u}").hostname or ""
    host = host.removeprefix("www.")
    return host or None


def normalize_phone(raw: str | None, region: str = "US") -> str | None:
    if not raw:
        return None
    try:
        n = phonenumbers.parse(raw, region)
    except phonenumbers.NumberParseException:
        return None
    if not phonenumbers.is_possible_number(n):
        return None
    return phonenumbers.format_number(n, phonenumbers.PhoneNumberFormat.E164)


def merge(a: Business, b: Business) -> Business:
    """Keep a's values; fill gaps from b; keep the larger review count."""
    data = a.model_dump()
    for k, v in b.model_dump().items():
        if data.get(k) in (None, ""):
            data[k] = v
    if a.reviews is not None and b.reviews is not None:
        data["reviews"] = max(a.reviews, b.reviews)
        if b.reviews > a.reviews and b.rating is not None:
            data["rating"] = b.rating
    return Business(**data)


def dedupe(items: list[Business], region: str = "US") -> list[Business]:
    """Collapse businesses sharing a normalized domain or phone."""
    out: list[Business] = []
    by_key: dict[str, int] = {}
    for b in items:
        keys = [k for k in (normalize_domain(b.website), normalize_phone(b.phone, region)) if k]
        idx = next((by_key[k] for k in keys if k in by_key), None)
        if idx is None:
            idx = len(out)
            out.append(b)
        else:
            out[idx] = merge(out[idx], b)
        for k in keys:
            by_key[k] = idx
    return out
