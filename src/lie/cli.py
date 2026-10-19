from __future__ import annotations

import asyncio
from pathlib import Path

import typer
from sqlmodel import Session

from . import pipeline
from .config import Settings
from .db import init_db, make_engine
from .export import export as export_leads
from .models import Query
from .opener import make_opener

app = typer.Typer(help="Lead Intel Engine: discover, enrich, score, export.", no_args_is_help=True)


def _db(settings: Settings) -> Session:
    engine = make_engine(settings.db_path)
    init_db(engine)
    return Session(engine)


def _settings(demo: bool | None, db: str | None) -> Settings:
    s = Settings.from_env()
    if demo is not None:
        s.demo_mode = demo
    if db:
        s.db_path = db
    return s


DEMO = typer.Option(None, "--demo/--live", help="Override DEMO_MODE env.")
DB = typer.Option(None, "--db", help="SQLite path (default: LIE_DB or lie.db).")


@app.command()
def discover(
    niche: str = typer.Option("", help="e.g. hvac"),
    city: str = typer.Option("", help="e.g. Dallas"),
    source: str = typer.Option("fixture", help="fixture | csv | places"),
    path: Path | None = typer.Option(None, help="CSV file for --source csv"),
    limit: int = 20,
    demo: bool | None = DEMO,
    db: str | None = DB,
):
    """Find businesses and store them (deduped)."""
    s = _settings(demo, db)
    q = Query(niche=niche, city=city, limit=limit, path=str(path) if path else None)
    with _db(s) as session:
        n = asyncio.run(pipeline.discover(session, s, source, q))
    typer.echo(f"{n} new leads")


@app.command()
def enrich(limit: int = 100, demo: bool | None = DEMO, db: str | None = DB):
    """Fetch each lead's website and extract contact and tech signals."""
    s = _settings(demo, db)

    async def go(session: Session) -> int:
        fetcher = pipeline.make_fetcher(s)
        try:
            return await pipeline.enrich(session, s, fetcher, limit)
        finally:
            await fetcher.aclose()

    with _db(s) as session:
        typer.echo(f"{asyncio.run(go(session))} sites enriched")


@app.command()
def score(
    opener: bool = typer.Option(True, "--opener/--no-opener", help="Generate opener lines."),
    rescore: bool = False,
    demo: bool | None = DEMO,
    db: str | None = DB,
):
    """Score leads 0-100 and (optionally) write an opener line."""
    s = _settings(demo, db)
    with _db(s) as session:
        n = asyncio.run(pipeline.score(session, make_opener(s, opener), rescore))
    typer.echo(f"{n} leads scored")


@app.command()
def export(
    out: Path = typer.Option(Path("leads.csv"), "--out", "-o"),
    fmt: str = typer.Option("csv", "--format", "-f", help="csv | json"),
    min_score: int = 0,
    demo: bool | None = DEMO,
    db: str | None = DB,
):
    """Write the lead list to CSV or JSON."""
    s = _settings(demo, db)
    with _db(s) as session:
        n = export_leads(session, out, fmt, min_score)
    typer.echo(f"{n} leads -> {out}")


@app.command()
def run(
    niche: str = typer.Option(...),
    city: str = typer.Option(...),
    source: str = typer.Option("fixture"),
    path: Path | None = typer.Option(None),
    limit: int = 20,
    out: Path = typer.Option(Path("leads.csv"), "--out", "-o"),
    fmt: str = typer.Option("csv", "--format", "-f"),
    demo: bool | None = DEMO,
    db: str | None = DB,
):
    """Discover, enrich, score, and export in one go."""
    s = _settings(demo, db)
    q = Query(niche=niche, city=city, limit=limit, path=str(path) if path else None)
    with _db(s) as session:
        stats = asyncio.run(pipeline.run(session, s, source, q, make_opener(s, True)))
        n = export_leads(session, out, fmt)
    typer.echo(f"{stats} -> {n} leads in {out}")


@app.command()
def serve(host: str = "127.0.0.1", port: int = 8000):
    """Start the FastAPI service."""
    import uvicorn

    uvicorn.run("lie.api:create_app", host=host, port=port, factory=True)
