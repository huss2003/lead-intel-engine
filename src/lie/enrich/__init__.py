from __future__ import annotations

from ..models import Business, Enrichment
from .extract import contact_url, extract
from .fetcher import Fetcher


def site_url(website: str) -> str:
    return website if "://" in website else f"https://{website}"


async def enrich_business(b: Business, fetcher: Fetcher, region: str = "US") -> Enrichment | None:
    """Fetch homepage and contact page, then extract signals. None if site unreachable."""
    if not b.website:
        return None
    home = site_url(b.website)
    html = await fetcher.fetch(home)
    if html is None:
        return None
    pages = {home: html}
    if (c := contact_url(html, home)) and c != home and (chtml := await fetcher.fetch(c)):
        pages[c] = chtml
    return extract(pages, region)
