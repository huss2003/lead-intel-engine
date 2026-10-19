from __future__ import annotations

import csv
import json
from pathlib import Path

from sqlmodel import Session, select

from .db import Lead

COLUMNS = [
    "score",
    "name",
    "website",
    "domain",
    "email",
    "phone",
    "city",
    "niche",
    "rating",
    "reviews",
    "cms",
    "hours",
    "socials",
    "reasons",
    "opener",
]


def lead_dict(r: Lead) -> dict:
    b, e = r.biz, r.enr
    return {
        "id": r.id,
        "score": r.score,
        "name": b.name,
        "website": b.website,
        "domain": r.domain,
        "email": e.emails[0] if e and e.emails else None,
        "emails": e.emails if e else [],
        "phone": (e.phones[0] if e and e.phones else None) or b.phone,
        "city": b.city,
        "niche": b.niche,
        "rating": b.rating,
        "reviews": b.reviews,
        "cms": e.cms if e else None,
        "hours": e.hours_text if e else None,
        "socials": e.socials if e else {},
        "reasons": r.reasons,
        "opener": r.opener,
    }


def query_leads(db: Session, min_score: int = 0) -> list[dict]:
    rows = db.exec(select(Lead).where(Lead.score >= min_score)).all()
    return sorted((lead_dict(r) for r in rows), key=lambda d: -(d["score"] or 0))


def export(db: Session, path: Path, fmt: str = "csv", min_score: int = 0) -> int:
    leads = query_leads(db, min_score)
    if fmt == "json":
        path.write_text(json.dumps(leads, indent=2), encoding="utf-8")
    else:
        with path.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=COLUMNS, extrasaction="ignore")
            w.writeheader()
            for d in leads:
                d = {
                    **d,
                    "socials": " ".join(d["socials"].values()),
                    "reasons": " | ".join(d["reasons"]),
                }
                w.writerow(d)
    return len(leads)
