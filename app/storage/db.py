from pathlib import Path

from sqlalchemy import Column, Date, DateTime, Integer, MetaData, Table, Text, create_engine
from sqlalchemy.engine import make_url

DEFAULT_DATABASE_URL = "sqlite:///data/app.db"

metadata = MetaData()

topics = Table(
    "topics",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("title", Text, nullable=False),
    Column("due_date", Date, nullable=False),
    Column("created_at", DateTime, nullable=False),
)


def get_engine(url=DEFAULT_DATABASE_URL):
    parsed = make_url(url)
    if parsed.drivername.startswith("sqlite") and parsed.database not in (None, "", ":memory:"):
        Path(parsed.database).parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(url)
    metadata.create_all(engine)
    return engine
