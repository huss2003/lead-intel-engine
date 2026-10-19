from __future__ import annotations

from sqlalchemy import JSON, Column
from sqlalchemy.pool import StaticPool
from sqlmodel import Field, Session, SQLModel, create_engine, select

from .dedupe import merge, normalize_domain, normalize_phone
from .models import Business, Enrichment


class Lead(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    domain: str | None = Field(default=None, index=True)
    phone_norm: str | None = Field(default=None, index=True)
    business: dict = Field(default_factory=dict, sa_column=Column(JSON))
    enrichment: dict | None = Field(default=None, sa_column=Column(JSON))
    score: int | None = None
    reasons: list = Field(default_factory=list, sa_column=Column(JSON))
    opener: str | None = None
    status: str = "discovered"  # discovered -> enriched -> scored

    @property
    def biz(self) -> Business:
        return Business(**self.business)

    @property
    def enr(self) -> Enrichment | None:
        return Enrichment(**self.enrichment) if self.enrichment else None


def make_engine(path: str):
    if path == ":memory:":
        return create_engine(
            "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
    return create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})


def init_db(engine) -> None:
    SQLModel.metadata.create_all(engine)


def upsert_business(s: Session, b: Business, region: str = "US") -> bool:
    """Insert or merge by normalized domain/phone. Returns True if a new row was created."""
    dom, ph = normalize_domain(b.website), normalize_phone(b.phone, region)
    row = None
    if dom:
        row = s.exec(select(Lead).where(Lead.domain == dom)).first()
    if row is None and ph:
        row = s.exec(select(Lead).where(Lead.phone_norm == ph)).first()
    if row is None:
        s.add(Lead(domain=dom, phone_norm=ph, business=b.model_dump()))
        s.commit()
        return True
    merged = merge(row.biz, b)
    row.business = merged.model_dump()
    row.domain = row.domain or dom
    row.phone_norm = row.phone_norm or ph
    s.add(row)
    s.commit()
    return False
