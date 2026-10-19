from __future__ import annotations

import httpx

from ..models import Business, Query

URL = "https://places.googleapis.com/v1/places:searchText"
MASK = (
    "places.id,places.displayName,places.websiteUri,places.nationalPhoneNumber,"
    "places.formattedAddress,places.rating,places.userRatingCount"
)


class PlacesSource:
    """Google Places API (New) Text Search. Requires GOOGLE_PLACES_API_KEY."""

    name = "places"

    def __init__(self, key: str | None, client: httpx.AsyncClient | None = None):
        self.key, self.client = key, client

    async def discover(self, q: Query) -> list[Business]:
        if not self.key:
            raise RuntimeError("GOOGLE_PLACES_API_KEY is not set (or use --source fixture/csv)")
        body = {"textQuery": f"{q.niche} in {q.city}", "pageSize": min(q.limit, 20)}
        headers = {"X-Goog-Api-Key": self.key, "X-Goog-FieldMask": MASK}
        client = self.client or httpx.AsyncClient(timeout=15)
        try:
            r = await client.post(URL, json=body, headers=headers)
            r.raise_for_status()
        finally:
            if self.client is None:
                await client.aclose()
        return [
            Business(
                name=p.get("displayName", {}).get("text", ""),
                website=p.get("websiteUri"),
                phone=p.get("nationalPhoneNumber"),
                address=p.get("formattedAddress"),
                rating=p.get("rating"),
                reviews=p.get("userRatingCount"),
                niche=q.niche,
                city=q.city,
                source=self.name,
            )
            for p in r.json().get("places", [])
            if p.get("displayName")
        ]
