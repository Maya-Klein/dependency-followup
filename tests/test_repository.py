from datetime import date

import pytest

from app.storage.db import get_engine
from app.storage.repository import (
    MAX_OUTCOME_LENGTH,
    MAX_TITLE_LENGTH,
    add_topic,
    delete_topic,
    get_topic,
    list_topics,
    update_topic,
)

OUTCOME = "אישור כתוב מהספק"
DUE = date(2026, 11, 3)


def test_saved_topic_survives_new_connection(db_url):
    add_topic(get_engine(db_url), "תשובה מהספק", date(2026, 11, 3), OUTCOME)

    rows = list_topics(get_engine(db_url))

    assert len(rows) == 1
    assert rows[0]["title"] == "תשובה מהספק"
    assert rows[0]["due_date"] == date(2026, 11, 3)


@pytest.mark.parametrize("title", ["", "   ", "\t\n"])
def test_blank_title_rejected_and_nothing_saved(engine, title):
    with pytest.raises(ValueError):
        add_topic(engine, title, date(2026, 11, 3), OUTCOME)

    assert list_topics(engine) == []


def test_title_length_limit(engine):
    add_topic(engine, "x" * MAX_TITLE_LENGTH, date(2026, 11, 3), OUTCOME)
    with pytest.raises(ValueError):
        add_topic(engine, "x" * (MAX_TITLE_LENGTH + 1), date(2026, 11, 3), OUTCOME)

    assert len(list_topics(engine)) == 1


def test_title_is_trimmed(engine):
    add_topic(engine, "  x  ", date(2026, 11, 3), OUTCOME)

    assert list_topics(engine)[0]["title"] == "x"


def test_html_title_stored_verbatim(engine):
    add_topic(engine, "<script>alert(1)</script>", date(2026, 11, 3), OUTCOME)

    assert list_topics(engine)[0]["title"] == "<script>alert(1)</script>"


def test_sorted_by_due_date_then_id(engine):
    add_topic(engine, "late", date(2026, 12, 1), OUTCOME)
    add_topic(engine, "early", date(2026, 11, 1), OUTCOME)
    add_topic(engine, "early-second", date(2026, 11, 1), OUTCOME)

    assert [r["title"] for r in list_topics(engine)] == ["early", "early-second", "late"]


def test_outcome_saved_and_trimmed(engine):
    topic_id = add_topic(engine, "x", DUE, "  שורה א\nשורה ב  ")

    assert get_topic(engine, topic_id)["required_outcome"] == "שורה א\nשורה ב"


@pytest.mark.parametrize("outcome", ["", "   ", "\t\n"])
def test_blank_outcome_rejected_and_nothing_saved(engine, outcome):
    with pytest.raises(ValueError, match="outcome_blank"):
        add_topic(engine, "x", DUE, outcome)

    assert list_topics(engine) == []


def test_outcome_length_limit(engine):
    add_topic(engine, "x", DUE, "y" * MAX_OUTCOME_LENGTH)
    with pytest.raises(ValueError, match="outcome_too_long"):
        add_topic(engine, "x", DUE, "y" * (MAX_OUTCOME_LENGTH + 1))

    assert len(list_topics(engine)) == 1


def test_html_outcome_stored_verbatim(engine):
    topic_id = add_topic(engine, "x", DUE, "<b>y</b>")

    assert get_topic(engine, topic_id)["required_outcome"] == "<b>y</b>"


def test_get_topic_missing_returns_none(engine):
    assert get_topic(engine, 999) is None


def test_update_topic_changes_fields(engine):
    topic_id = add_topic(engine, "old", DUE, OUTCOME)

    assert update_topic(engine, topic_id, "  new  ", date(2026, 12, 1), "תוצאה חדשה") is True

    topic = get_topic(engine, topic_id)
    assert (topic["title"], topic["due_date"], topic["required_outcome"]) == ("new", date(2026, 12, 1), "תוצאה חדשה")


@pytest.mark.parametrize("title, outcome", [("", OUTCOME), ("x", ""), ("x" * (MAX_TITLE_LENGTH + 1), OUTCOME)])
def test_update_topic_invalid_leaves_topic_unchanged(engine, title, outcome):
    topic_id = add_topic(engine, "old", DUE, OUTCOME)

    with pytest.raises(ValueError):
        update_topic(engine, topic_id, title, date(2026, 12, 1), outcome)

    topic = get_topic(engine, topic_id)
    assert (topic["title"], topic["due_date"], topic["required_outcome"]) == ("old", DUE, OUTCOME)


def test_update_topic_missing_returns_false(engine):
    assert update_topic(engine, 999, "x", DUE, OUTCOME) is False


def test_delete_topic_removes_only_that_topic(engine):
    gone = add_topic(engine, "gone", DUE, OUTCOME)
    kept = add_topic(engine, "kept", DUE, OUTCOME)

    assert delete_topic(engine, gone) is True

    assert get_topic(engine, gone) is None
    assert [t["id"] for t in list_topics(engine)] == [kept]


def test_delete_topic_missing_returns_false(engine):
    assert delete_topic(engine, 999) is False
