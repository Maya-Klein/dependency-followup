from datetime import datetime, timezone

from sqlalchemy import delete, insert, select, update

from app.storage.db import topics


MAX_TITLE_LENGTH = 200
MAX_OUTCOME_LENGTH = 2000


def clean_topic_fields(title, required_outcome):
    """Trim and validate; ValueError's message is the code of the first problem found."""
    title = (title or "").strip()
    required_outcome = (required_outcome or "").strip()
    if not title:
        raise ValueError("title_blank")
    if len(title) > MAX_TITLE_LENGTH:
        raise ValueError("title_too_long")
    if not required_outcome:
        raise ValueError("outcome_blank")
    if len(required_outcome) > MAX_OUTCOME_LENGTH:
        raise ValueError("outcome_too_long")
    return title, required_outcome


def add_topic(engine, title, due_date, required_outcome):
    title, required_outcome = clean_topic_fields(title, required_outcome)
    with engine.begin() as conn:
        result = conn.execute(
            insert(topics).values(
                title=title,
                required_outcome=required_outcome,
                due_date=due_date,
                created_at=datetime.now(timezone.utc).replace(tzinfo=None),
            )
        )
    return result.inserted_primary_key[0]


def list_topics(engine):
    stmt = select(topics).order_by(topics.c.due_date, topics.c.id)
    with engine.connect() as conn:
        return [dict(row) for row in conn.execute(stmt).mappings()]


def get_topic(engine, topic_id):
    with engine.connect() as conn:
        row = conn.execute(select(topics).where(topics.c.id == topic_id)).mappings().first()
    return dict(row) if row else None


def update_topic(engine, topic_id, title, due_date, required_outcome):
    """Returns False if the topic does not exist."""
    title, required_outcome = clean_topic_fields(title, required_outcome)
    with engine.begin() as conn:
        result = conn.execute(
            update(topics)
            .where(topics.c.id == topic_id)
            .values(title=title, required_outcome=required_outcome, due_date=due_date)
        )
    return result.rowcount > 0


def delete_topic(engine, topic_id):
    """Returns False if the topic does not exist."""
    with engine.begin() as conn:
        result = conn.execute(delete(topics).where(topics.c.id == topic_id))
    return result.rowcount > 0
