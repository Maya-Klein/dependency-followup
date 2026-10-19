from datetime import date

from flask import Blueprint, current_app, redirect, render_template, request, url_for

from app.core.deadlines import LEVEL_LABELS, days_remaining, days_text, today_in_israel, urgency_level
from app.storage.repository import MAX_TITLE_LENGTH, add_topic, list_topics

bp = Blueprint("main", __name__)


def _render_index(status=200, error=None, title="", due=""):
    today = today_in_israel()
    items = []
    for topic in list_topics(current_app.config["ENGINE"]):
        days = days_remaining(topic["due_date"], today)
        level = urgency_level(days)
        items.append(
            {
                **topic,
                "days_text": days_text(days),
                "level": level,
                "label": LEVEL_LABELS[level],
            }
        )
    html = render_template(
        "index.html",
        items=items,
        error=error,
        title=title,
        due=due,
        max_title=MAX_TITLE_LENGTH,
    )
    return html, status


@bp.get("/")
def index():
    return _render_index()


@bp.post("/")
def create():
    title = request.form.get("title", "")
    due = request.form.get("due_date", "")

    try:
        due_date = date.fromisoformat(due)
    except ValueError:
        return _render_index(400, "יש להזין תאריך תקין", title, due)

    if len(title.strip()) > MAX_TITLE_LENGTH:
        return _render_index(400, f"הכותרת ארוכה מדי (עד {MAX_TITLE_LENGTH} תווים)", title, due)

    try:
        add_topic(current_app.config["ENGINE"], title, due_date)
    except ValueError:
        return _render_index(400, "יש להזין כותרת", title, due)

    return redirect(url_for("main.index"), code=303)
