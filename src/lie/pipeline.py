from __future__ import annotations

import asyncio

from sqlmodel import Session, select

from .config import Settings
from .db import Lead, upsert_business
from .discover import make_source
from .enrich import enrich_business
from .enrich.fetcher import Crawl4AIFetcher, Fetcher, FixtureFetcher, HttpFetcher
from .models import Query
from .opener import OpenerGenerator
from .score import score_lead


def make_fetcher(s: Settings) -> Fetcher:
    if s.demo_mode:
        return FixtureFetcher()
    cls = Crawl4AIFetcher if s.fetcher == "crawl4ai" else HttpFetcher
    return cls(s.user_agent, s.timeout, s.retries, s.concurrency, s.domain_delay)


async def discover(db: Session, settings: Settings, source: str, q: Query) -> int:
    found = await make_source(source, settings).discover(q)
    return sum(upsert_business(db, b, settings.default_region) for b in found)


async def enrich(db: Session, settings: Settings, fetcher: Fetcher, limit: int = 100) -> int:
    rows = db.exec(select(Lead).where(Lead.status == "discovered").limit(limit)).all()
    results = await asyncio.gather(
        *(enrich_business(r.biz, fetcher, settings.default_region) for r in rows)
    )
    for row, enr in zip(rows, results, strict=True):
        row.enrichment = enr.model_dump() if enr else None
        row.status = "enriched"
        db.add(row)
    db.commit()
    return sum(e is not None for e in results)


async def score(db: Session, opener: OpenerGenerator | None = None, rescore: bool = False) -> int:
    stmt = select(Lead) if rescore else select(Lead).where(Lead.status != "scored")
    rows = db.exec(stmt).all()
    for row in rows:
        sc = score_lead(row.biz, row.enr)
        row.score, row.reasons, row.status = sc.score, sc.reasons, "scored"
        if opener and not row.opener:
            row.opener = await opener.generate(row.biz, row.enr, sc)
        db.add(row)
    db.commit()
    return len(rows)


async def run(
    db: Session,
    settings: Settings,
    source: str,
    q: Query,
    opener: OpenerGenerator | None = None,
    fetcher: Fetcher | None = None,
) -> dict[str, int]:
    fetcher = fetcher or make_fetcher(settings)
    try:
        new = await discover(db, settings, source, q)
        enriched = await enrich(db, settings, fetcher)
    finally:
        await fetcher.aclose()
    scored = await score(db, opener)
    return {"discovered": new, "enriched": enriched, "scored": scored}
