from __future__ import annotations

from typing import Protocol

from ..config import Settings
from ..models import Business, Query


class Source(Protocol):
    name: str

    async def discover(self, q: Query) -> list[Business]: ...


def make_source(name: str, settings: Settings) -> Source:
    from .csv_source import CsvSource
    from .fixture import FixtureSource
    from .places import PlacesSource

    sources = {
        "fixture": lambda: FixtureSource(),
        "csv": lambda: CsvSource(),
        "places": lambda: PlacesSource(settings.places_key),
    }
    if name not in sources:
        raise ValueError(f"unknown source {name!r}; choose from {sorted(sources)}")
    return sources[name]()
