from __future__ import annotations

from pydantic import BaseModel, Field


class Query(BaseModel):
    niche: str = ""
    city: str = ""
    limit: int = 20
    path: str | None = None  # CSV source only


class Business(BaseModel):
    name: str
    website: str | None = None
    phone: str | None = None
    address: str | None = None
    rating: float | None = None
    reviews: int | None = None
    niche: str = ""
    city: str = ""
    source: str = ""


class Enrichment(BaseModel):
    emails: list[str] = Field(default_factory=list)
    phones: list[str] = Field(default_factory=list)
    socials: dict[str, str] = Field(default_factory=dict)
    has_chat: bool = False
    has_booking: bool = False
    has_ads: bool = False
    cms: str | None = None
    hours_text: str | None = None
    open_24_7: bool = False
    pages: list[str] = Field(default_factory=list)


class Score(BaseModel):
    score: int
    reasons: list[str]
