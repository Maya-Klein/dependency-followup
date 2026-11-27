"""How a saved analysis is ordered, counted and checked for age. Pure functions, no AI."""

from app.core.analysis import CONFIRMED, MISSING, NO_LONGER_REQUIRED, PROCEEDING, REPORTED_DONE

# What needs attention comes first
STATE_ORDER = (MISSING, PROCEEDING, REPORTED_DONE, CONFIRMED, NO_LONGER_REQUIRED)


def sort_rows(items):
    """By state; inside one state the model's order is kept (sorted is stable)."""
    return sorted(items, key=lambda row: STATE_ORDER.index(row["state"]))


def state_counts(items):
    """(state, count) pairs in display order, only for states that appear."""
    counts = ((state, sum(row["state"] == state for row in items)) for state in STATE_ORDER)
    return [(state, count) for state, count in counts if count]


def is_stale(analysis, topic, update_ids):
    """True if the topic's updates, required outcome or deadline are not the ones that were analysed."""
    return (
        set(analysis["update_ids"]) != set(update_ids)
        or analysis["required_outcome"] != topic["required_outcome"]
        or analysis["due_date"] != topic["due_date"]
    )
