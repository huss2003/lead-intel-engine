from __future__ import annotations

import re
from urllib.parse import urljoin, urlparse

import phonenumbers
from selectolax.lexbor import LexborHTMLParser as HTMLParser

from ..models import Enrichment

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")
JUNK_EMAIL = re.compile(r"\.(png|jpe?g|gif|svg|webp)$|^(sentry|noreply|no-reply|example)@", re.I)
SOCIALS = {
    "facebook.com": "facebook",
    "instagram.com": "instagram",
    "linkedin.com": "linkedin",
    "twitter.com": "twitter",
    "x.com": "twitter",
    "youtube.com": "youtube",
    "tiktok.com": "tiktok",
    "yelp.com": "yelp",
}
CHAT = (
    "intercom",
    "drift.com",
    "tawk.to",
    "livechatinc",
    "crisp.chat",
    "tidio",
    "podium",
    "birdeye",
    "olark",
    "zopim",
    "hs-scripts.com/conversations",
    "widget.manychat",
)
BOOKING = (
    "calendly",
    "acuityscheduling",
    "setmore",
    "housecallpro",
    "jobber.com",
    "servicetitan",
    "schedulicity",
    "book online",
    "schedule online",
    "book now",
    "schedule service",
)
ADS = (
    "googleadservices",
    "gclid",
    "fbq(",
    "connect.facebook.net",
    "doubleclick",
    "googleads",
    "msclkid",
)
CMS = (
    ("wp-content", "WordPress"),
    ("wixstatic", "Wix"),
    ("squarespace", "Squarespace"),
    ("cdn.shopify", "Shopify"),
    ("webflow", "Webflow"),
    ("godaddy", "GoDaddy"),
)
HOURS_RE = re.compile(
    r"((?:mon|tue|wed|thu|fri|sat|sun)[a-z]*\.?\s*(?:[-–to&,]+\s*(?:mon|tue|wed|thu|fri|sat|sun)"
    r"[a-z]*\.?\s*)?:?\s*\d{1,2}(?::\d{2})?\s*(?:am|pm)\s*[-–to]+\s*\d{1,2}(?::\d{2})?\s*(?:am|pm))",
    re.I,
)
H247 = re.compile(r"24\s*/\s*7|24\s*hours|open 24|24-hour", re.I)


def contact_url(html: str, base: str) -> str | None:
    """Find a same-site link that looks like the contact page."""
    host = urlparse(base).netloc
    for a in HTMLParser(html).css("a[href]"):
        href = a.attributes.get("href") or ""
        if "contact" in href.lower() or "contact" in (a.text() or "").lower():
            full = urljoin(base, href)
            if urlparse(full).netloc == host and not full.startswith("mailto:"):
                return full
    return None


def extract(pages: dict[str, str], region: str = "US") -> Enrichment:
    """Build an Enrichment from {url: html}. Pure function; no I/O."""
    emails: set[str] = set()
    phones: dict[str, None] = {}
    socials: dict[str, str] = {}
    hours: str | None = None
    open247 = False
    blob = ""
    for html in pages.values():
        tree = HTMLParser(html)
        blob += html.lower()
        for a in tree.css("a[href]"):
            href = (a.attributes.get("href") or "").strip()
            if href.lower().startswith("mailto:"):
                emails.add(href[7:].split("?")[0].strip().lower())
            elif href.lower().startswith("tel:"):
                _add_phone(phones, href[4:], region)
            else:
                host = (urlparse(href).hostname or "").removeprefix("www.")
                for dom, label in SOCIALS.items():
                    if host == dom or host.endswith("." + dom):
                        socials.setdefault(label, href)
        for bad in tree.css("script, style, noscript"):
            bad.decompose()
        text = tree.body.text(separator=" ") if tree.body else ""
        text = re.sub(r"\s+", " ", text)
        emails.update(m.lower() for m in EMAIL_RE.findall(text))
        for m in phonenumbers.PhoneNumberMatcher(text, region):
            _add_phone(phones, m.raw_string, region)
        open247 = open247 or bool(H247.search(text))
        if hours is None and (m := HOURS_RE.search(text)):
            hours = m.group(1).strip()
    return Enrichment(
        emails=sorted(e for e in emails if not JUNK_EMAIL.search(e)),
        phones=list(phones),
        socials=socials,
        has_chat=any(s in blob for s in CHAT),
        has_booking=any(s in blob for s in BOOKING),
        has_ads=any(s in blob for s in ADS) or bool(re.search(r"['\"/=]aw-\d", blob)),
        cms=next((name for sig, name in CMS if sig in blob), None),
        hours_text=hours,
        open_24_7=open247,
        pages=list(pages),
    )


def _add_phone(acc: dict[str, None], raw: str, region: str) -> None:
    try:
        n = phonenumbers.parse(raw, region)
    except phonenumbers.NumberParseException:
        return
    if phonenumbers.is_valid_number(n):
        acc[phonenumbers.format_number(n, phonenumbers.PhoneNumberFormat.E164)] = None
