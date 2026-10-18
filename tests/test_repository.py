from datetime import date

import pytest

from app.storage.db import get_engine
from app.storage.repository import add_topic, list_topics


def test_saved_topic_survives_new_connection(db_url):
    add_topic(get_engine(db_url), "תשובה מהספק", date(2026, 11, 3))

    rows = list_topics(get_engine(db_url))

    assert len(rows) == 1
    assert rows[0]["title"] == "תשובה מהספק"
    assert rows[0]["due_date"] == date(2026, 11, 3)


@pytest.mark.parametrize("title", ["", "   ", "\t\n"])
def test_blank_title_rejected_and_nothing_saved(engine, title):
    with pytest.raises(ValueError):
        add_topic(engine, title, date(2026, 11, 3))

    assert list_topics(engine) == []


def test_title_is_trimmed(engine):
    add_topic(engine, "  x  ", date(2026, 11, 3))

    assert list_topics(engine)[0]["title"] == "x"


def test_html_title_stored_verbatim(engine):
    add_topic(engine, "<script>alert(1)</script>", date(2026, 11, 3))

    assert list_topics(engine)[0]["title"] == "<script>alert(1)</script>"


def test_sorted_by_due_date_then_id(engine):
    add_topic(engine, "late", date(2026, 12, 1))
    add_topic(engine, "early", date(2026, 11, 1))
    add_topic(engine, "early-second", date(2026, 11, 1))

    assert [r["title"] for r in list_topics(engine)] == ["early", "early-second", "late"]
