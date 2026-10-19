from __future__ import annotations

from collections.abc import Callable

from .models import Business, Enrichment, Score

# Transparent weights; they sum to 100. Edit here to retune.
WEIGHTS = {
    "rating": 15,
    "reviews": 20,
    "no_chat": 20,
    "no_booking": 20,
    "after_hours": 15,
    "ads": 10,
}

Rule = Callable[[Business, Enrichment | None], tuple[int, str]]


def _rating(b: Business, e: Enrichment | None) -> tuple[int, str]:
    w = WEIGHTS["rating"]
    r = b.rating
    if r is None:
        return 0, "No rating data"
    if r >= 4.3:
        return w, f"Strong rating ({r}): reputation worth protecting"
    if r >= 4.0:
        return round(w * 0.67), f"Good rating ({r})"
    if r >= 3.5:
        return round(w * 0.33), f"Average rating ({r})"
    return 0, f"Weak rating ({r}): likely a service problem, not a call-handling one"


def _reviews(b: Business, e: Enrichment | None) -> tuple[int, str]:
    w, n = WEIGHTS["reviews"], b.reviews
    if n is None:
        return 0, "No review count"
    if n >= 100:
        return w, f"{n} reviews: high call volume likely"
    if n >= 30:
        return round(w * 0.7), f"{n} reviews: steady demand"
    if n >= 10:
        return round(w * 0.4), f"{n} reviews: some demand"
    return 0, f"Only {n} reviews: low volume"


def _no_chat(b: Business, e: Enrichment | None) -> tuple[int, str]:
    if e is None:
        return 0, "Site not enriched: chat widget unknown"
    if e.has_chat:
        return 0, "Already has a live chat widget"
    return WEIGHTS["no_chat"], "No live chat widget on site"


def _no_booking(b: Business, e: Enrichment | None) -> tuple[int, str]:
    if e is None:
        return 0, "Site not enriched: booking unknown"
    if e.has_booking:
        return 0, "Already offers online booking"
    return WEIGHTS["no_booking"], "No online booking"


def _after_hours(b: Business, e: Enrichment | None) -> tuple[int, str]:
    if e is None:
        return 0, "Site not enriched: hours unknown"
    if e.open_24_7:
        return 0, "Advertises 24/7 coverage"
    if e.hours_text:
        return WEIGHTS["after_hours"], f"After-hours gap (hours: {e.hours_text})"
    return round(WEIGHTS["after_hours"] / 2), "No hours published: coverage gap probable"


def _ads(b: Business, e: Enrichment | None) -> tuple[int, str]:
    if e is not None and e.has_ads:
        return WEIGHTS["ads"], "Runs ad tracking: pays for leads, so missed calls cost money"
    return 0, "No ad signals"


RULES: tuple[Rule, ...] = (_rating, _reviews, _no_chat, _no_booking, _after_hours, _ads)


def score_lead(b: Business, e: Enrichment | None) -> Score:
    pts, reasons = 0, []
    for rule in RULES:
        p, why = rule(b, e)
        pts += p
        reasons.append(f"{'+' if p else ' '}{p}: {why}" if p else f"0: {why}")
    return Score(score=max(0, min(100, pts)), reasons=reasons)
