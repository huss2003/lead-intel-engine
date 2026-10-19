from __future__ import annotations

from typing import Protocol

import httpx

from .config import Settings
from .models import Business, Enrichment, Score


class OpenerGenerator(Protocol):
    async def generate(self, b: Business, e: Enrichment | None, s: Score) -> str: ...


def _gap(e: Enrichment | None) -> str:
    if e is None:
        return "calls that go unanswered"
    if not e.has_chat and not e.has_booking:
        return "after-hours calls and web inquiries with no chat or booking to catch them"
    if not e.has_booking:
        return "callers who want to book but can't online"
    return "after-hours calls"


class MockOpener:
    """Deterministic template opener for DEMO_MODE and tests."""

    async def generate(self, b: Business, e: Enrichment | None, s: Score) -> str:
        proof = (
            f"{b.reviews} reviews at {b.rating} stars"
            if b.reviews and b.rating
            else "your reputation"
        )
        return (
            f"Hi {b.name} team, with {proof} you're clearly busy. "
            f"Are you losing {_gap(e)}? A 24/7 AI receptionist could answer them."
        )


class AnthropicOpener:
    """One-line cold-email opener via the Anthropic Messages API."""

    def __init__(self, key: str, model: str, client: httpx.AsyncClient | None = None):
        self.key, self.model, self.client = key, model, client

    async def generate(self, b: Business, e: Enrichment | None, s: Score) -> str:
        prompt = (
            "Write ONE friendly, specific opening sentence (max 30 words, no hype, no emojis) "
            "for a cold email offering an AI phone receptionist to this local business.\n"
            f"Business: {b.name} ({b.niche}, {b.city}); rating {b.rating}, {b.reviews} reviews.\n"
            f"Observed gaps: {'; '.join(s.reasons)}\nReturn only the sentence."
        )
        client = self.client or httpx.AsyncClient(timeout=30)
        try:
            r = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={"x-api-key": self.key, "anthropic-version": "2023-06-01"},
                json={
                    "model": self.model,
                    "max_tokens": 120,
                    "messages": [{"role": "user", "content": prompt}],
                },
            )
            r.raise_for_status()
        finally:
            if self.client is None:
                await client.aclose()
        return r.json()["content"][0]["text"].strip()


def make_opener(settings: Settings, enabled: bool) -> OpenerGenerator | None:
    if not enabled:
        return None
    if settings.demo_mode or not settings.anthropic_key:
        return MockOpener()
    return AnthropicOpener(settings.anthropic_key, settings.anthropic_model)
