from pathlib import Path

import pytest
from sqlmodel import Session

from lie.db import init_db, make_engine

FIX = Path(__file__).parent / "fixtures"


def html(name: str) -> str:
    return (FIX / name).read_text(encoding="utf-8")


@pytest.fixture
def db():
    engine = make_engine(":memory:")
    init_db(engine)
    with Session(engine) as s:
        yield s
