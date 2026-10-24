from datetime import date

from flask import Blueprint, abort, current_app, redirect, render_template, request, url_for
from flask_wtf.csrf import CSRFError

from app.core.deadlines import (
    LEVEL_LABELS,
    TODAY,
    TOMORROW,
    days_remaining,
    days_text,
    israel_date,
    today_in_israel,
    urgency_level,
)
from app.core.updates import excerpt
from app.storage.repository import (
    MAX_OUTCOME_LENGTH,
    MAX_TITLE_LENGTH,
    MAX_UPDATE_LENGTHS,
    THREAD,
    USER_SUMMARY,
    add_topic,
    add_update,
    clean_topic_fields,
    clean_update_fields,
    delete_topic,
    delete_update,
    get_topic,
    get_update,
    list_topics,
    list_updates,
    normalize_update_text,
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
UPDATE_ERRORS = {
    "kind_invalid": "יש לבחור סוג עדכון",
    "content_blank": "יש להזין את תוכן העדכון",
}
FUTURE_DATE_ERROR = "אי אפשר להזין תאריך עתידי"
KIND_LABELS = {THREAD: "ציטוט מהתכתבות", USER_SUMMARY: "סיכום שיחה או פגישה"}
TOO_LONG_ERRORS = {
    THREAD: (
        "הטקסט ארוך מדי: {length:,} תווים, והמותר הוא {limit:,}. "
        "אפשר להסיר חלקים שחוזרים על עצמם, כמו מיילים קודמים שמצוטטים שוב או חתימות. "
        "אפשר גם לחלק את הטקסט לשני חלקים ולשמור כל חלק כעדכון נפרד"
    ),
    USER_SUMMARY: (
        "הסיכום ארוך מדי: {length:,} תווים, והמותר הוא {limit:,}. "
        "אפשר לקצר אותו, או לחלק אותו לשני חלקים ולשמור כל חלק כעדכון נפרד"
    ),
}


def _engine():
    return current_app.config["ENGINE"]


def _decorate(topic, today):
    days = days_remaining(topic["due_date"], today)
    level = urgency_level(days)
    return {
        **topic,
        "days_text": days_text(days),
        # display only: the badge already says "היום" / "מחר", so the days text would repeat it
        "show_days": level not in (TODAY, TOMORROW),
        "level": level,
        "label": LEVEL_LABELS[level],
    }


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


def _update_form(today, kind="", content="", entry=None):
    return {"kind": kind, "content": content, "entry": today.isoformat() if entry is None else entry}


def _read_update_form(today):
    """Returns (form, cleaned kind, cleaned content, entry_date, error); error is a Hebrew message or None."""
    form = _update_form(
        today,
        request.form.get("kind", ""),
        request.form.get("content", ""),
        request.form.get("entry_date", ""),
    )
    try:
        entry_date = date.fromisoformat(form["entry"])
    except ValueError:
        return form, None, None, None, DATE_ERROR
    if entry_date > today:
        return form, None, None, None, FUTURE_DATE_ERROR
    try:
        kind, content = clean_update_fields(form["kind"], form["content"])
    except ValueError as exc:
        if str(exc) == "content_too_long":
            length = len(normalize_update_text(form["content"]))
            limit = MAX_UPDATE_LENGTHS[form["kind"]]
            return form, None, None, None, TOO_LONG_ERRORS[form["kind"]].format(length=length, limit=limit)
        return form, None, None, None, UPDATE_ERRORS[str(exc)]
    return form, kind, content, entry_date, None


def _render_detail(topic, status=200, error=None, form=None):
    today = today_in_israel()
    entries = [
        {**u, "excerpt": excerpt(u["content"]), "entered": israel_date(u["created_at"])}
        for u in list_updates(_engine(), topic["id"])
    ]
    html = render_template(
        "topic.html",
        topic=_decorate(topic, today),
        updates=entries,
        error=error,
        form=form or _update_form(today),
        today=today,
        THREAD=THREAD,
        USER_SUMMARY=USER_SUMMARY,
        KIND_LABELS=KIND_LABELS,
    )
    return html, status


def _update_or_404(topic_id, update_id):
    update = get_update(_engine(), update_id)
    if update is None or update["topic_id"] != topic_id:
        abort(404)
    return update


@bp.app_errorhandler(404)
def not_found(_error):
    return render_template("404.html"), 404


@bp.app_errorhandler(413)
def too_large(_error):
    return render_template("too_large.html"), 413


@bp.app_errorhandler(CSRFError)
def csrf_failed(_error):
    return render_template("csrf_error.html"), 400


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
    return _render_detail(_topic_or_404(topic_id))


@bp.post("/topics/<int:topic_id>/updates")
def add_update_route(topic_id):
    topic = _topic_or_404(topic_id)
    form, kind, content, entry_date, error = _read_update_form(today_in_israel())
    if error:
        return _render_detail(topic, 400, error, form)

    add_update(_engine(), topic_id, kind, content, entry_date)
    return redirect(url_for("main.detail", topic_id=topic_id), code=303)


@bp.get("/topics/<int:topic_id>/updates/<int:update_id>/delete")
def delete_update_confirm(topic_id, update_id):
    topic = _topic_or_404(topic_id)
    update = _update_or_404(topic_id, update_id)
    return render_template(
        "update_delete.html",
        topic=topic,
        update=update,
        excerpt=excerpt(update["content"]),
        kind_label=KIND_LABELS[update["kind"]],
    )


@bp.post("/topics/<int:topic_id>/updates/<int:update_id>/delete")
def delete_update_route(topic_id, update_id):
    _topic_or_404(topic_id)
    _update_or_404(topic_id, update_id)
    delete_update(_engine(), update_id)
    return redirect(url_for("main.detail", topic_id=topic_id), code=303)


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
