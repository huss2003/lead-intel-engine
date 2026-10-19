from __future__ import annotations

import csv

from ..models import Business, Query

ALIASES = {
    "name": ("name", "business", "business_name", "company"),
    "website": ("website", "url", "site", "domain"),
    "phone": ("phone", "telephone", "tel"),
    "address": ("address", "street"),
    "rating": ("rating", "stars"),
    "reviews": ("reviews", "review_count", "user_ratings_total"),
    "niche": ("niche", "category", "industry"),
    "city": ("city",),
}


def _num(v: str | None, cast):
    try:
        return cast(float(v)) if v not in (None, "") else None
    except ValueError:
        return None


class CsvSource:
    name = "csv"

    async def discover(self, q: Query) -> list[Business]:
        if not q.path:
            raise ValueError("csv source needs --path")
        out: list[Business] = []
        with open(q.path, newline="", encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                low = {k.strip().lower(): (v or "").strip() for k, v in row.items() if k}
                pick = {
                    f: next((low[a] for a in al if low.get(a)), "") for f, al in ALIASES.items()
                }
                if not pick["name"]:
                    continue
                out.append(
                    Business(
                        name=pick["name"],
                        website=pick["website"] or None,
                        phone=pick["phone"] or None,
                        address=pick["address"] or None,
                        rating=_num(pick["rating"], float),
                        reviews=_num(pick["reviews"], int),
                        niche=pick["niche"] or q.niche,
                        city=pick["city"] or q.city,
                        source=self.name,
                    )
                )
        return out[: q.limit]
