from datetime import datetime, timezone

from sqlalchemy import delete, insert, select, update

from app.storage.db import topics, updates


MAX_TITLE_LENGTH = 200
MAX_OUTCOME_LENGTH = 2000

# By form, not by channel: pasted written text vs. the user's own words about something said aloud
THREAD = "thread"
USER_SUMMARY = "user_summary"
# The thread limit only guards against a huge paste; saving a whole thread matters more than keeping it short
MAX_UPDATE_LENGTHS = {THREAD: 200000, USER_SUMMARY: 5000}


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
    """Returns False if the topic does not exist. Its updates are deleted with it (ON DELETE CASCADE)."""
    with engine.begin() as conn:
        result = conn.execute(delete(topics).where(topics.c.id == topic_id))
    return result.rowcount > 0


def normalize_update_text(content):
    """Trim the ends and use \\n for line breaks; nothing else in the text is touched."""
    return (content or "").replace("\r\n", "\n").replace("\r", "\n").strip()


def clean_update_fields(kind, content):
    """Normalise and validate; ValueError's message is the code of the first problem found."""
    if kind not in MAX_UPDATE_LENGTHS:
        raise ValueError("kind_invalid")
    content = normalize_update_text(content)
    if not content:
        raise ValueError("content_blank")
    if len(content) > MAX_UPDATE_LENGTHS[kind]:
        raise ValueError("content_too_long")
    return kind, content


def add_update(engine, topic_id, kind, content, entry_date):
    kind, content = clean_update_fields(kind, content)
    with engine.begin() as conn:
        result = conn.execute(
            insert(updates).values(
                topic_id=topic_id,
                kind=kind,
                content=content,
                entry_date=entry_date,
                created_at=datetime.now(timezone.utc).replace(tzinfo=None),
            )
        )
    return result.inserted_primary_key[0]


def list_updates(engine, topic_id):
    """Newest first: by entry date, then by the order they were added."""
    stmt = (
        select(updates)
        .where(updates.c.topic_id == topic_id)
        .order_by(updates.c.entry_date.desc(), updates.c.id.desc())
    )
    with engine.connect() as conn:
        return [dict(row) for row in conn.execute(stmt).mappings()]


def get_update(engine, update_id):
    with engine.connect() as conn:
        row = conn.execute(select(updates).where(updates.c.id == update_id)).mappings().first()
    return dict(row) if row else None


def delete_update(engine, update_id):
    """Only for an update entered by mistake; there is no edit. Returns False if it does not exist."""
    with engine.begin() as conn:
        result = conn.execute(delete(updates).where(updates.c.id == update_id))
    return result.rowcount > 0
