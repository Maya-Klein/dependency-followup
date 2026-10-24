from pathlib import Path

from sqlalchemy import Column, Date, DateTime, ForeignKey, Integer, MetaData, Table, Text, create_engine, event
from sqlalchemy.engine import make_url

DEFAULT_DATABASE_URL = "sqlite:///data/app.db"

metadata = MetaData()

topics = Table(
    "topics",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("title", Text, nullable=False),
    Column("required_outcome", Text, nullable=False),
    Column("due_date", Date, nullable=False),
    Column("created_at", DateTime, nullable=False),
)

# Append-only history: an update is added or deleted, never edited. Deleting a topic deletes its updates.
updates = Table(
    "updates",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("topic_id", Integer, ForeignKey("topics.id", ondelete="CASCADE"), nullable=False, index=True),
    Column("kind", Text, nullable=False),
    Column("content", Text, nullable=False),
    Column("entry_date", Date, nullable=False),
    Column("created_at", DateTime, nullable=False),
)


def get_engine(url=DEFAULT_DATABASE_URL):
    parsed = make_url(url)
    if parsed.drivername.startswith("sqlite") and parsed.database not in (None, "", ":memory:"):
        Path(parsed.database).parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(url)
    if parsed.drivername.startswith("sqlite"):
        # SQLite ignores foreign keys (and so ON DELETE CASCADE) unless this is set on every connection
        @event.listens_for(engine, "connect")
        def _enable_foreign_keys(dbapi_connection, _record):
            dbapi_connection.execute("PRAGMA foreign_keys=ON")

    metadata.create_all(engine)
    return engine
