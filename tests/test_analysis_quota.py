import sqlite3
import threading
from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.engine import make_url

from app.storage.db import analysis_calls
from app.storage.repository import (
    USER_SUMMARY,
    add_topic,
    add_update,
    delete_topic,
    delete_update,
    reserve_analysis_call,
)

DAY = date(2026, 11, 27)


def _count(engine, day=DAY):
    stmt = select(func.count()).select_from(analysis_calls).where(analysis_calls.c.call_date == day)
    with engine.connect() as conn:
        return conn.execute(stmt).scalar_one()


def test_a_call_is_refused_when_the_quota_is_full(engine):
    assert reserve_analysis_call(engine, 1, DAY, 2)
    assert reserve_analysis_call(engine, 2, DAY, 2)  # all topics share the quota
    assert not reserve_analysis_call(engine, 1, DAY, 2)
    assert _count(engine) == 2


def test_zero_limit_refuses_the_first_call(engine):
    assert not reserve_analysis_call(engine, 1, DAY, 0)
    assert _count(engine) == 0


def test_the_quota_starts_again_the_next_day(engine):
    tomorrow = DAY + timedelta(days=1)
    assert reserve_analysis_call(engine, 1, DAY, 1)
    assert reserve_analysis_call(engine, 1, tomorrow, 1)
    assert not reserve_analysis_call(engine, 1, tomorrow, 1)


def test_deleting_an_update_or_a_topic_does_not_give_quota_back(engine):
    topic_id = add_topic(engine, "נושא", DAY, "תוצאה")
    update_id = add_update(engine, topic_id, USER_SUMMARY, "סיכום", DAY)
    assert reserve_analysis_call(engine, topic_id, DAY, 1)

    assert delete_update(engine, update_id)
    assert delete_topic(engine, topic_id)

    assert _count(engine) == 1
    assert not reserve_analysis_call(engine, topic_id, DAY, 1)


def test_a_second_writer_counts_only_after_the_first_commits(engine, db_url):
    """Deterministic version of two clicks at once: the first one holds the write lock, uncommitted."""
    limit = 2
    first = sqlite3.connect(make_url(db_url).database, isolation_level=None)
    first.execute("BEGIN IMMEDIATE")
    for _ in range(limit):
        first.execute(
            "INSERT INTO analysis_calls (call_date, topic_id, created_at) VALUES (?, 1, ?)",
            (DAY.isoformat(), "2026-11-27 10:00:00.000000"),
        )
    results = []
    second = threading.Thread(target=lambda: results.append(reserve_analysis_call(engine, 1, DAY, limit)))
    second.start()
    second.join(0.5)
    waiting = second.is_alive()
    first.execute("COMMIT")
    first.close()
    second.join(10)

    assert waiting
    assert results == [False]
    assert _count(engine) == limit


def test_parallel_calls_never_pass_the_limit(engine):
    threads, limit = 10, 3
    for round_number in range(20):
        day = DAY + timedelta(days=round_number)
        barrier = threading.Barrier(threads)
        results = []

        def click():
            barrier.wait()
            results.append(reserve_analysis_call(engine, 1, day, limit))

        workers = [threading.Thread(target=click) for _ in range(threads)]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join()

        assert sorted(results) == [False] * (threads - limit) + [True] * limit
        assert _count(engine, day) == limit
