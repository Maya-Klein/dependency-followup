from datetime import date

from flask import Blueprint, abort, current_app, redirect, render_template, request, url_for

from app.core.deadlines import LEVEL_LABELS, days_remaining, days_text, today_in_israel, urgency_level
from app.storage.repository import (
    MAX_OUTCOME_LENGTH,
    MAX_TITLE_LENGTH,
    add_topic,
    clean_topic_fields,
    delete_topic,
    get_topic,
    list_topics,
    update_topic,
)

bp = Blueprint("main", __name__)

DATE_ERROR = "יש להזין תאריך תקין"
FIELD_ERRORS = {
    "title_blank": "יש להזין כותרת",
    "title_too_long": f"הכותרת ארוכה מדי (עד {MAX_TITLE_LENGTH} תווים)",
    "outcome_blank": "יש להזין תוצאה נדרשת",
    "outcome_too_long": f"התוצאה הנדרשת ארוכה מדי (עד {MAX_OUTCOME_LENGTH} תווים)",
}
EMPTY_FORM = {"title": "", "required_outcome": "", "due": ""}


def _engine():
    return current_app.config["ENGINE"]


def _decorate(topic, today):
    days = days_remaining(topic["due_date"], today)
    level = urgency_level(days)
    return {**topic, "days_text": days_text(days), "level": level, "label": LEVEL_LABELS[level]}


def _topic_or_404(topic_id):
    topic = get_topic(_engine(), topic_id)
    if topic is None:
        abort(404)
    return topic


def _read_form():
    """Returns (form, due_date, error); error is a Hebrew message or None."""
    form = {
        "title": request.form.get("title", ""),
        "required_outcome": request.form.get("required_outcome", ""),
        "due": request.form.get("due_date", ""),
    }
    try:
        due_date = date.fromisoformat(form["due"])
    except ValueError:
        return form, None, DATE_ERROR
    try:
        clean_topic_fields(form["title"], form["required_outcome"])
    except ValueError as exc:
        return form, None, FIELD_ERRORS[str(exc)]
    return form, due_date, None


def _render_index(status=200, error=None, form=EMPTY_FORM):
    today = today_in_israel()
    items = [_decorate(topic, today) for topic in list_topics(_engine())]
    html = render_template(
        "index.html",
        items=items,
        error=error,
        form=form,
        max_title=MAX_TITLE_LENGTH,
        max_outcome=MAX_OUTCOME_LENGTH,
    )
    return html, status


def _render_edit(topic, status=200, error=None, form=None):
    if form is None:
        form = {
            "title": topic["title"],
            "required_outcome": topic["required_outcome"],
            "due": topic["due_date"].isoformat(),
        }
    html = render_template(
        "topic_edit.html",
        topic=topic,
        error=error,
        form=form,
        max_title=MAX_TITLE_LENGTH,
        max_outcome=MAX_OUTCOME_LENGTH,
    )
    return html, status


@bp.app_errorhandler(404)
def not_found(_error):
    return render_template("404.html"), 404


@bp.get("/")
def index():
    return _render_index()


@bp.post("/")
def create():
    form, due_date, error = _read_form()
    if error:
        return _render_index(400, error, form)

    add_topic(_engine(), form["title"], due_date, form["required_outcome"])
    return redirect(url_for("main.index"), code=303)


@bp.get("/topics/<int:topic_id>")
def detail(topic_id):
    topic = _decorate(_topic_or_404(topic_id), today_in_israel())
    return render_template("topic.html", topic=topic)


@bp.get("/topics/<int:topic_id>/edit")
def edit_form(topic_id):
    return _render_edit(_topic_or_404(topic_id))


@bp.post("/topics/<int:topic_id>/edit")
def edit(topic_id):
    topic = _topic_or_404(topic_id)
    form, due_date, error = _read_form()
    if error:
        return _render_edit(topic, 400, error, form)

    update_topic(_engine(), topic_id, form["title"], due_date, form["required_outcome"])
    return redirect(url_for("main.detail", topic_id=topic_id), code=303)


@bp.get("/topics/<int:topic_id>/delete")
def delete_confirm(topic_id):
    return render_template("topic_delete.html", topic=_topic_or_404(topic_id))


@bp.post("/topics/<int:topic_id>/delete")
def delete(topic_id):
    if not delete_topic(_engine(), topic_id):
        abort(404)
    return redirect(url_for("main.index"), code=303)
