import sqlite3
from datetime import date, datetime

import pytest
from sqlalchemy import text

from app.core.deadlines import israel_date
from app.core.updates import EXCERPT_MAX_CHARS, EXCERPT_MAX_LINES, excerpt
from app.storage.db import get_engine
from app.storage.repository import (
    MAX_UPDATE_LENGTHS,
    THREAD,
    USER_SUMMARY,
    add_topic,
    add_update,
    delete_topic,
    delete_update,
    get_topic,
    get_update,
    list_topics,
    list_updates,
)

DUE = date(2026, 11, 3)


@pytest.fixture
def topic_id(engine):
    return add_topic(engine, "נושא", DUE, "תוצאה")


# --- repository ---


def test_two_updates_are_two_separate_records_newest_first(engine, topic_id):
    older = add_update(engine, topic_id, THREAD, "ראשון", date(2026, 10, 10))
    newer = add_update(engine, topic_id, USER_SUMMARY, "שני", date(2026, 10, 12))

    rows = list_updates(engine, topic_id)

    assert [r["id"] for r in rows] == [newer, older]
    assert [r["content"] for r in rows] == ["שני", "ראשון"]


def test_same_entry_date_is_ordered_by_id_descending(engine, topic_id):
    first = add_update(engine, topic_id, THREAD, "א", date(2026, 10, 10))
    second = add_update(engine, topic_id, THREAD, "ב", date(2026, 10, 10))

    assert [r["id"] for r in list_updates(engine, topic_id)] == [second, first]


def test_update_of_one_topic_is_not_listed_for_another(engine, topic_id):
    other = add_topic(engine, "אחר", DUE, "תוצאה")
    add_update(engine, topic_id, THREAD, "רק לנושא הראשון", date(2026, 10, 10))

    assert list_updates(engine, other) == []


@pytest.mark.parametrize("kind", ["manual", "", None, "THREAD", "summary"])
def test_invalid_kind_is_rejected(engine, topic_id, kind):
    with pytest.raises(ValueError, match="kind_invalid"):
        add_update(engine, topic_id, kind, "טקסט", date(2026, 10, 10))

    assert list_updates(engine, topic_id) == []


@pytest.mark.parametrize("content", ["", "   ", "\n\t \r\n", None])
def test_blank_content_is_rejected(engine, topic_id, content):
    with pytest.raises(ValueError, match="content_blank"):
        add_update(engine, topic_id, THREAD, content, date(2026, 10, 10))


@pytest.mark.parametrize("kind", [THREAD, USER_SUMMARY])
def test_length_limit_boundary(engine, topic_id, kind):
    limit = MAX_UPDATE_LENGTHS[kind]

    add_update(engine, topic_id, kind, "א" * limit, date(2026, 10, 10))
    with pytest.raises(ValueError, match="content_too_long"):
        add_update(engine, topic_id, kind, "א" * (limit + 1), date(2026, 10, 10))

    assert len(list_updates(engine, topic_id)) == 1


def test_limits_are_50000_for_thread_and_5000_for_summary():
    assert MAX_UPDATE_LENGTHS == {THREAD: 50000, USER_SUMMARY: 5000}


def test_text_is_trimmed_and_line_breaks_normalised_but_otherwise_kept(engine, topic_id):
    add_update(engine, topic_id, THREAD, "  שורה א\r\n\r\n> ציטוט 😀 <b>x</b>\rסוף  \n", date(2026, 10, 10))

    assert list_updates(engine, topic_id)[0]["content"] == "שורה א\n\n> ציטוט 😀 <b>x</b>\nסוף"


def test_long_mixed_language_text_is_stored_whole(engine, topic_id):
    body = ("Hello שלום 😀 <script>alert(1)</script>\n" * 1000).strip()

    add_update(engine, topic_id, THREAD, body, date(2026, 10, 10))

    assert list_updates(engine, topic_id)[0]["content"] == body


def test_saved_update_survives_new_connection(db_url, topic_id, engine):
    add_update(engine, topic_id, USER_SUMMARY, "נשמר", date(2026, 10, 10))

    rows = list_updates(get_engine(db_url), topic_id)

    assert rows[0]["content"] == "נשמר"
    assert rows[0]["kind"] == USER_SUMMARY
    assert rows[0]["entry_date"] == date(2026, 10, 10)
    assert rows[0]["created_at"] is not None


def test_delete_update_removes_only_that_one(engine, topic_id):
    keep = add_update(engine, topic_id, THREAD, "נשאר", date(2026, 10, 10))
    gone = add_update(engine, topic_id, THREAD, "נמחק", date(2026, 10, 11))

    assert delete_update(engine, gone) is True

    assert [r["id"] for r in list_updates(engine, topic_id)] == [keep]
    assert get_update(engine, gone) is None


def test_delete_missing_update_returns_false(engine):
    assert delete_update(engine, 999) is False


def test_foreign_keys_are_on_for_every_connection(engine):
    for _ in range(2):
        with engine.connect() as conn:
            assert conn.execute(text("PRAGMA foreign_keys")).scalar() == 1


def test_deleting_a_topic_deletes_its_updates_only(engine, topic_id):
    other = add_topic(engine, "אחר", DUE, "תוצאה")
    add_update(engine, topic_id, THREAD, "יימחק", date(2026, 10, 10))
    kept = add_update(engine, other, THREAD, "יישאר", date(2026, 10, 10))

    assert delete_topic(engine, topic_id) is True

    assert list_updates(engine, topic_id) == []
    assert [r["id"] for r in list_updates(engine, other)] == [kept]


def test_existing_db_without_updates_table_opens_and_keeps_topics(db_url, tmp_path):
    path = tmp_path / "test.db"
    raw = sqlite3.connect(path)
    raw.execute(
        "CREATE TABLE topics (id INTEGER PRIMARY KEY, title TEXT NOT NULL, required_outcome TEXT NOT NULL,"
        " due_date DATE NOT NULL, created_at DATETIME NOT NULL)"
    )
    raw.execute("INSERT INTO topics VALUES (1, 'ישן', 'תוצאה', '2026-11-03', '2026-10-01 08:00:00')")
    raw.commit()
    raw.close()

    engine = get_engine(db_url)

    assert [t["title"] for t in list_topics(engine)] == ["ישן"]
    assert list_updates(engine, 1) == []
    add_update(engine, 1, THREAD, "חדש", date(2026, 10, 10))
    assert get_topic(engine, 1)["title"] == "ישן"


# --- core ---


def test_israel_date_of_naive_utc_crosses_midnight():
    assert israel_date(datetime(2026, 10, 18, 20, 59)) == date(2026, 10, 18)
    assert israel_date(datetime(2026, 10, 18, 21, 30)) == date(2026, 10, 19)  # UTC+3 before the clocks change


def test_excerpt_is_none_for_a_short_update():
    assert excerpt("שורה\n" * (EXCERPT_MAX_LINES - 1) + "אחרונה") is None
    assert excerpt("א" * EXCERPT_MAX_CHARS) is None


def test_excerpt_cuts_long_text_by_characters():
    cut = excerpt("א" * (EXCERPT_MAX_CHARS + 1))

    assert cut == "א" * EXCERPT_MAX_CHARS + "…"


def test_excerpt_cuts_many_lines():
    cut = excerpt("\n".join(f"שורה {i}" for i in range(1, EXCERPT_MAX_LINES + 2)))

    assert cut.count("\n") == EXCERPT_MAX_LINES - 1
    assert cut.endswith("שורה 8…")


def test_excerpt_ends_with_ellipsis_when_cut_mid_text():
    assert excerpt("שלום " * 200).endswith("שלום…")


@pytest.mark.parametrize("mark", [".", "!", "?", ",", ":", ";", ")", '"', "…"])
def test_excerpt_has_no_ellipsis_after_existing_punctuation(mark):
    text = "א" * (EXCERPT_MAX_CHARS - 1) + mark + "ב" * 50

    cut = excerpt(text)

    assert cut == text[:EXCERPT_MAX_CHARS]
    assert cut.endswith(mark) and not cut.endswith("……")


def test_excerpt_checks_punctuation_after_trimming_trailing_whitespace():
    lines = ["שורה."] + ["ש"] * 7 + ["עוד"]

    assert excerpt("\n".join(lines)) == "\n".join(lines[:-1]) + "…"
    assert excerpt("\n".join(["ש"] * 7 + ["סוף.", "עוד"])) == "\n".join(["ש"] * 7 + ["סוף."])
