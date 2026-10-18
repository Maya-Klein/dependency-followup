from datetime import datetime, timezone

from sqlalchemy import insert, select

from app.storage.db import topics


MAX_TITLE_LENGTH = 200


def add_topic(engine, title, due_date):
    title = (title or "").strip()
    if not title:
        raise ValueError("title must not be blank")
    if len(title) > MAX_TITLE_LENGTH:
        raise ValueError("title too long")
    with engine.begin() as conn:
        result = conn.execute(
            insert(topics).values(
                title=title,
                due_date=due_date,
                created_at=datetime.now(timezone.utc).replace(tzinfo=None),
            )
        )
    return result.inserted_primary_key[0]


def list_topics(engine):
    stmt = select(topics).order_by(topics.c.due_date, topics.c.id)
    with engine.connect() as conn:
        return [dict(row) for row in conn.execute(stmt).mappings()]
