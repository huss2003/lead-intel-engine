from __future__ import annotations

import json
from importlib import resources

from ..models import Business, Query


class FixtureSource:
    """Offline demo businesses shipped with the package."""

    name = "fixture"

    async def discover(self, q: Query) -> list[Business]:
        raw = json.loads(
            resources.files("lie.data").joinpath("fixture_businesses.json").read_text("utf-8")
        )
        out = []
        for r in raw:
            if q.niche and r["niche"].lower() != q.niche.lower():
                continue
            out.append(Business(**r, city=q.city or r.get("city", ""), source=self.name))
        return out[: q.limit]
