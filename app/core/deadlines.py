from datetime import datetime
from zoneinfo import ZoneInfo

ISRAEL_TZ = ZoneInfo("Asia/Jerusalem")

# Thresholds in days remaining; the only place they are defined.
FAR_MIN_DAYS = 6
APPROACHING_MIN_DAYS = 2

FAR = "far"
APPROACHING = "approaching"
TOMORROW = "tomorrow"
TODAY = "today"
OVERDUE = "overdue"

LEVEL_LABELS = {
    FAR: "רחוק",
    APPROACHING: "מתקרב",
    TOMORROW: "מחר",
    TODAY: "היום",
    OVERDUE: "באיחור",
}


def today_in_israel(now=None):
    """Today's calendar date in Israel; `now` must be timezone-aware if given."""
    now = now or datetime.now(ISRAEL_TZ)
    return now.astimezone(ISRAEL_TZ).date()


def days_remaining(due, today):
    return (due - today).days


def urgency_level(days):
    if days >= FAR_MIN_DAYS:
        return FAR
    if days >= APPROACHING_MIN_DAYS:
        return APPROACHING
    if days == 1:
        return TOMORROW
    if days == 0:
        return TODAY
    return OVERDUE
