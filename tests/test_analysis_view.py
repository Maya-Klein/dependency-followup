from datetime import date

import pytest

from app.core.analysis import CONFIRMED, MISSING, NO_LONGER_REQUIRED, PROCEEDING, REPORTED_DONE, STATES
from app.core.analysis_view import STATE_ORDER, is_stale, sort_rows, state_counts


def _rows(*pairs):
    return [{"item": item, "state": state} for item, state in pairs]


def test_every_state_has_a_place_in_the_order():
    assert sorted(STATE_ORDER) == sorted(STATES)


def test_sort_by_state_and_keep_the_models_order_inside_a_state():
    items = _rows(
        ("a", NO_LONGER_REQUIRED),
        ("b", CONFIRMED),
        ("c", MISSING),
        ("d", REPORTED_DONE),
        ("e", PROCEEDING),
        ("f", MISSING),
    )

    assert [row["item"] for row in sort_rows(items)] == ["c", "f", "e", "d", "b", "a"]
    assert [row["item"] for row in items] == ["a", "b", "c", "d", "e", "f"]


def test_counts_in_display_order_without_zeros():
    items = _rows(("a", CONFIRMED), ("b", MISSING), ("c", MISSING))

    assert state_counts(items) == [(MISSING, 2), (CONFIRMED, 1)]


def test_empty_analysis():
    assert sort_rows([]) == []
    assert state_counts([]) == []


ANALYSIS = {"update_ids": [2, 1], "required_outcome": "תוצאה", "due_date": date(2026, 12, 10)}
TOPIC = {"required_outcome": "תוצאה", "due_date": date(2026, 12, 10)}


def test_not_stale_when_nothing_changed_even_if_the_order_of_updates_differs():
    assert not is_stale(ANALYSIS, TOPIC, [1, 2])


@pytest.mark.parametrize(
    "topic_change, update_ids",
    [
        ({}, [1, 2, 3]),  # a new update
        ({}, [1]),  # a deleted update
        ({"required_outcome": "תוצאה אחרת"}, [1, 2]),
        ({"due_date": date(2026, 12, 11)}, [1, 2]),
    ],
)
def test_stale_when_something_it_was_run_against_changed(topic_change, update_ids):
    assert is_stale(ANALYSIS, {**TOPIC, **topic_change}, update_ids)
