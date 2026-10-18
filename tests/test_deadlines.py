from datetime import date, datetime, timezone

import pytest

from app.core.deadlines import days_remaining, today_in_israel, urgency_level


@pytest.mark.parametrize(
    "days, level",
    [
        (100, "far"),
        (7, "far"),
        (6, "far"),
        (5, "approaching"),
        (3, "approaching"),
        (2, "approaching"),
        (1, "tomorrow"),
        (0, "today"),
        (-1, "overdue"),
        (-30, "overdue"),
    ],
)
def test_urgency_level(days, level):
    assert urgency_level(days) == level


@pytest.mark.parametrize(
    "today, due, expected",
    [
        (date(2026, 1, 31), date(2026, 2, 1), 1),  # month boundary
        (date(2026, 12, 31), date(2027, 1, 1), 1),  # year boundary
        (date(2028, 2, 28), date(2028, 3, 1), 2),  # leap year
        (date(2026, 10, 18), date(2026, 10, 18), 0),
        (date(2026, 10, 18), date(2026, 10, 17), -1),
    ],
)
def test_days_remaining(today, due, expected):
    assert days_remaining(due, today) == expected


def test_today_in_israel_after_utc_evening_is_next_day():
    now = datetime(2026, 10, 18, 22, 30, tzinfo=timezone.utc)
    assert today_in_israel(now) == date(2026, 10, 19)


def test_today_in_israel_midday_same_day():
    now = datetime(2026, 10, 18, 12, 0, tzinfo=timezone.utc)
    assert today_in_israel(now) == date(2026, 10, 18)
