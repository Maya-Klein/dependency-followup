from datetime import date

import pytest
from sqlalchemy import func, select

from app.storage.db import analyses
from app.storage.repository import (
    USER_SUMMARY,
    add_analysis,
    add_topic,
    add_update,
    delete_topic,
    delete_update,
    latest_analysis,
)

DUE = date(2026, 12, 10)


@pytest.fixture
def topic_id(engine):
    return add_topic(engine, "נושא", DUE, "תוצאה")


def _update(engine, topic_id):
    return add_update(engine, topic_id, USER_SUMMARY, "סיכום", date(2026, 11, 1))


def _analysis(engine, topic_id, update_ids=(), result=None):
    return add_analysis(
        engine, topic_id, result or {"items": []}, {"model": "m"}, "תמר, Uri", update_ids, "תוצאה", DUE
    )


def _count(engine, topic_id):
    stmt = select(func.count()).select_from(analyses).where(analyses.c.topic_id == topic_id)
    with engine.connect() as conn:
        return conn.execute(stmt).scalar_one()


def test_latest_analysis_is_none_without_analyses(engine, topic_id):
    assert latest_analysis(engine, topic_id) is None
    assert latest_analysis(engine, 2**63) is None


def test_every_run_is_kept_and_latest_returns_the_newest(engine, topic_id):
    first = _analysis(engine, topic_id)
    result = {"items": [{"item": 'אישור <b>"בכתב"</b>', "findings": []}], "not_read": [[1, "2026-11-01"]]}
    second = _analysis(engine, topic_id, update_ids=[3, 1], result=result)

    row = latest_analysis(engine, topic_id)

    assert row["id"] == second != first
    assert row["result"] == result
    assert row["meta"] == {"model": "m"}
    assert row["update_ids"] == [3, 1]
    assert (row["our_side"], row["required_outcome"], row["due_date"]) == ("תמר, Uri", "תוצאה", DUE)
    assert _count(engine, topic_id) == 2


def test_deleting_an_update_deletes_all_analyses_of_its_topic_only(engine, topic_id):
    other = add_topic(engine, "אחר", DUE, "תוצאה")
    deleted = _update(engine, topic_id)
    _update(engine, topic_id)
    _analysis(engine, topic_id)
    _analysis(engine, topic_id)
    _analysis(engine, other)

    assert delete_update(engine, deleted)

    assert latest_analysis(engine, topic_id) is None
    assert _count(engine, other) == 1


def test_deleting_a_missing_update_keeps_the_analyses(engine, topic_id):
    _analysis(engine, topic_id)

    assert not delete_update(engine, 999)

    assert _count(engine, topic_id) == 1


def test_deleting_a_topic_deletes_its_analyses(engine, topic_id):
    _analysis(engine, topic_id)

    assert delete_topic(engine, topic_id)

    assert _count(engine, topic_id) == 0
