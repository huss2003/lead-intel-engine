from __future__ import annotations

import uuid

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from sqlmodel import Session

from . import pipeline
from .config import Settings
from .db import init_db, make_engine
from .export import query_leads
from .models import Query
from .opener import make_opener


class RunRequest(BaseModel):
    niche: str
    city: str
    source: str = "fixture"  # csv is CLI-only: the API must not read arbitrary server files
    limit: int = 20


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    engine = make_engine(settings.db_path)
    init_db(engine)
    api = FastAPI(title="Lead Intel Engine", version="0.1.0")

    @api.get("/health")
    def health():
        return {"ok": True, "demo_mode": settings.demo_mode}

    @api.post("/runs")
    async def create_run(req: RunRequest):
        if req.source not in {"fixture", "places"}:
            raise HTTPException(422, "source must be 'fixture' or 'places'")
        q = Query(niche=req.niche, city=req.city, limit=req.limit)
        try:
            with Session(engine) as db:
                stats = await pipeline.run(db, settings, req.source, q, make_opener(settings, True))
        except RuntimeError as e:
            raise HTTPException(400, str(e)) from e
        return {"run_id": uuid.uuid4().hex, **stats}

    @api.get("/leads")
    def leads(min_score: int = 0):
        with Session(engine) as db:
            return query_leads(db, min_score)

    return api
