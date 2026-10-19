from __future__ import annotations

import os

from pydantic import BaseModel


def _flag(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


class Settings(BaseModel):
    demo_mode: bool = False
    db_path: str = "lie.db"
    user_agent: str = "LeadIntelEngine/0.1 (+https://github.com/huss2003/lead-intel-engine)"
    concurrency: int = 5
    domain_delay: float = 2.0
    timeout: float = 10.0
    retries: int = 3
    fetcher: str = "httpx"
    default_region: str = "US"
    places_key: str | None = None
    anthropic_key: str | None = None
    anthropic_model: str = "claude-sonnet-4-5"

    @classmethod
    def from_env(cls) -> Settings:
        e = os.getenv
        return cls(
            demo_mode=_flag("DEMO_MODE"),
            db_path=e("LIE_DB", "lie.db"),
            user_agent=e("LIE_USER_AGENT", cls.model_fields["user_agent"].default),
            concurrency=int(e("LIE_CONCURRENCY", "5")),
            domain_delay=float(e("LIE_DOMAIN_DELAY", "2.0")),
            timeout=float(e("LIE_TIMEOUT", "10")),
            retries=int(e("LIE_RETRIES", "3")),
            fetcher=e("LIE_FETCHER", "httpx"),
            default_region=e("LIE_DEFAULT_REGION", "US"),
            places_key=e("GOOGLE_PLACES_API_KEY") or None,
            anthropic_key=e("ANTHROPIC_API_KEY") or None,
            anthropic_model=e("LIE_ANTHROPIC_MODEL", "claude-sonnet-4-5"),
        )
