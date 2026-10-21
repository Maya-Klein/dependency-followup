from datetime import date, timedelta

import pytest

from app.storage.repository import add_topic, get_topic, list_topics
from app.web import create_app

TODAY = date(2026, 10, 18)


@pytest.fixture
def app(db_url, monkeypatch):
    monkeypatch.setattr("app.web.routes.today_in_israel", lambda: TODAY)
    return create_app(db_url)


@pytest.fixture
def client(app):
    return app.test_client()


OUTCOME = "אישור כתוב מהספק"


def post(client, title, due, outcome=OUTCOME):
    return client.post("/", data={"title": title, "due_date": due, "required_outcome": outcome})


def add(app, title="נושא", due="2026-10-28", outcome=OUTCOME):
    return add_topic(app.config["ENGINE"], title, date.fromisoformat(due), outcome)


def edit_post(client, topic_id, title, due, outcome=OUTCOME):
    return client.post(
        f"/topics/{topic_id}/edit", data={"title": title, "due_date": due, "required_outcome": outcome}
    )


def test_index_is_rtl_hebrew(client):
    resp = client.get("/")

    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert 'dir="rtl"' in html
    assert 'lang="he"' in html


def test_valid_post_redirects_and_topic_is_listed(client):
    resp = post(client, "תשובה מהספק", "2026-10-28")

    assert resp.status_code == 303
    html = client.get("/").get_data(as_text=True)
    assert "תשובה מהספק" in html
    assert "level-far" in html
    assert '<bdi class="days">בעוד 10 ימים</bdi>' in html


@pytest.mark.parametrize(
    "offset, text",
    [(1, "בעוד יום"), (2, "בעוד יומיים"), (0, "היום"), (-1, "לפני יום"), (-2, "לפני יומיים")],
)
def test_days_text_rendered_in_page(client, offset, text):
    post(client, "x", (TODAY + timedelta(days=offset)).isoformat())

    assert f'<bdi class="days">{text}</bdi>' in client.get("/").get_data(as_text=True)


@pytest.mark.parametrize(
    "offset, level, label",
    [
        (10, "far", "בהמשך"),
        (3, "approaching", "מתקרב"),
        (1, "tomorrow", "מחר"),
        (0, "today", "היום"),
        (-1, "overdue", "באיחור"),
    ],
)
def test_each_level_is_rendered(client, offset, level, label):
    post(client, "x", (TODAY + timedelta(days=offset)).isoformat())

    html = client.get("/").get_data(as_text=True)

    assert f"level-{level}" in html
    assert f'<span class="badge">{label}</span>' in html


@pytest.mark.parametrize("title", ["", "   "])
def test_blank_title_rejected(client, app, title):
    resp = post(client, title, "2026-10-28")

    assert resp.status_code == 400
    assert "יש להזין כותרת" in resp.get_data(as_text=True)
    assert list_topics(app.config["ENGINE"]) == []


def test_too_long_title_rejected(client, app):
    resp = post(client, "x" * 201, "2026-10-28")

    assert resp.status_code == 400
    assert "הכותרת ארוכה מדי" in resp.get_data(as_text=True)
    assert list_topics(app.config["ENGINE"]) == []


def test_form_has_maxlength(client):
    assert 'maxlength="200"' in client.get("/").get_data(as_text=True)


@pytest.mark.parametrize("due", ["", "2026-02-30", "abc"])
def test_invalid_date_rejected(client, app, due):
    resp = post(client, "x", due)

    assert resp.status_code == 400
    assert "יש להזין תאריך תקין" in resp.get_data(as_text=True)
    assert list_topics(app.config["ENGINE"]) == []


def test_rejected_form_keeps_input(client):
    resp = post(client, "כותרת", "abc")

    assert 'value="כותרת"' in resp.get_data(as_text=True)


@pytest.mark.parametrize(
    "title, live, escaped",
    [
        ("<script>alert(1)</script>", "<script>alert(1)", "&lt;script&gt;alert(1)&lt;/script&gt;"),
        ("<b>x</b>", "<b>x</b>", "&lt;b&gt;x&lt;/b&gt;"),
    ],
)
def test_html_title_is_escaped(client, title, live, escaped):
    post(client, title, "2026-10-28")

    html = client.get("/").get_data(as_text=True)

    assert escaped in html
    assert live not in html


def test_fresh_page_has_no_error_and_form_is_closed(client):
    html = client.get("/").get_data(as_text=True)

    assert 'role="alert"' not in html
    assert 'class="error"' not in html
    assert '<details class="add">' in html


@pytest.mark.parametrize(
    "title, due",
    [("", "2026-10-28"), ("x" * 201, "2026-10-28"), ("x", "abc")],
)
def test_rejected_post_opens_form_and_error_has_no_trailing_period(client, title, due):
    html = post(client, title, due).get_data(as_text=True)

    assert '<details class="add" open>' in html
    error = html.split('role="alert">')[1].split("</p>")[0]
    assert error and not error.endswith(".")


# --- required outcome ---


@pytest.mark.parametrize("outcome", ["", "   "])
def test_blank_outcome_rejected(client, app, outcome):
    resp = post(client, "x", "2026-10-28", outcome)

    assert resp.status_code == 400
    assert "יש להזין תוצאה נדרשת" in resp.get_data(as_text=True)
    assert list_topics(app.config["ENGINE"]) == []


def test_too_long_outcome_rejected(client, app):
    resp = post(client, "x", "2026-10-28", "y" * 2001)

    assert resp.status_code == 400
    assert "התוצאה הנדרשת ארוכה מדי" in resp.get_data(as_text=True)
    assert list_topics(app.config["ENGINE"]) == []


def test_form_has_outcome_textarea_with_maxlength(client):
    html = client.get("/").get_data(as_text=True)

    assert '<textarea name="required_outcome"' in html
    assert 'maxlength="2000"' in html


def test_rejected_form_keeps_outcome(client):
    html = post(client, "", "2026-10-28", "תוצאה כלשהי").get_data(as_text=True)

    assert "תוצאה כלשהי</textarea>" in html


# --- detail page ---


def test_list_links_to_detail(client, app):
    topic_id = add(app)

    assert f'href="/topics/{topic_id}"' in client.get("/").get_data(as_text=True)


def test_detail_shows_topic(client, app):
    topic_id = add(app, "תשובה מהספק", "2026-10-21", "שורה א\nשורה ב")

    html = client.get(f"/topics/{topic_id}").get_data(as_text=True)

    assert "תשובה מהספק" in html
    assert "level-approaching" in html
    assert '<span class="badge">מתקרב</span>' in html
    assert '<bdi class="due">21/10/2026</bdi>' in html
    assert '<bdi class="days">בעוד 3 ימים</bdi>' in html
    assert "שורה א\nשורה ב" in html
    assert "עריכת הנושא" in html and "מחיקת הנושא" in html


def test_detail_of_overdue_topic_shows_overdue(client, app):
    topic_id = add(app, due="2026-10-15")

    html = client.get(f"/topics/{topic_id}").get_data(as_text=True)

    assert "level-overdue" in html
    assert '<bdi class="days">לפני 3 ימים</bdi>' in html


# --- edit ---


def test_edit_form_is_prefilled(client, app):
    topic_id = add(app, "כותרת", "2026-10-28", "תוצאה")

    html = client.get(f"/topics/{topic_id}/edit").get_data(as_text=True)

    assert 'value="כותרת"' in html
    assert 'value="2026-10-28"' in html
    assert "תוצאה</textarea>" in html


def test_edit_saves_changes(client, app):
    topic_id = add(app, "ישן", "2026-10-28", "תוצאה ישנה")

    resp = edit_post(client, topic_id, "חדש", "2026-11-05", "תוצאה חדשה")

    assert resp.status_code == 303
    assert resp.headers["Location"] == f"/topics/{topic_id}"
    topic = get_topic(app.config["ENGINE"], topic_id)
    assert (topic["title"], topic["due_date"], topic["required_outcome"]) == (
        "חדש",
        date(2026, 11, 5),
        "תוצאה חדשה",
    )


@pytest.mark.parametrize(
    "title, due, outcome, message",
    [
        ("", "2026-11-05", "x", "יש להזין כותרת"),
        ("x", "2026-11-05", "", "יש להזין תוצאה נדרשת"),
        ("x", "abc", "x", "יש להזין תאריך תקין"),
        ("x" * 201, "2026-11-05", "x", "הכותרת ארוכה מדי"),
    ],
)
def test_invalid_edit_rejected_and_topic_unchanged(client, app, title, due, outcome, message):
    topic_id = add(app, "ישן", "2026-10-28", "תוצאה ישנה")

    resp = edit_post(client, topic_id, title, due, outcome)

    assert resp.status_code == 400
    assert message in resp.get_data(as_text=True)
    topic = get_topic(app.config["ENGINE"], topic_id)
    assert (topic["title"], topic["due_date"], topic["required_outcome"]) == (
        "ישן",
        date(2026, 10, 28),
        "תוצאה ישנה",
    )


# --- delete ---


def test_delete_confirm_page_does_not_delete(client, app):
    topic_id = add(app, "למחיקה")

    html = client.get(f"/topics/{topic_id}/delete").get_data(as_text=True)

    assert "למחוק את הנושא" in html and "למחיקה" in html
    assert get_topic(app.config["ENGINE"], topic_id) is not None


def test_delete_removes_only_that_topic(client, app):
    gone = add(app, "נמחק")
    kept = add(app, "נשאר")

    resp = client.post(f"/topics/{gone}/delete")

    assert resp.status_code == 303
    assert resp.headers["Location"] == "/"
    assert [t["id"] for t in list_topics(app.config["ENGINE"])] == [kept]


# --- missing ids ---


@pytest.mark.parametrize(
    "method, path",
    [
        ("get", "/topics/999"),
        ("get", "/topics/999/edit"),
        ("post", "/topics/999/edit"),
        ("get", "/topics/999/delete"),
        ("post", "/topics/999/delete"),
    ],
)
def test_missing_topic_is_404_in_hebrew(client, method, path):
    resp = getattr(client, method)(path, data={"title": "x", "due_date": "2026-10-28", "required_outcome": "x"})

    assert resp.status_code == 404
    assert "הדף לא נמצא" in resp.get_data(as_text=True)


def test_delete_is_post_only(client, app):
    topic_id = add(app)

    assert client.put(f"/topics/{topic_id}/delete").status_code == 405
    assert client.delete(f"/topics/{topic_id}/delete").status_code == 405
    assert get_topic(app.config["ENGINE"], topic_id) is not None


# --- escaping in the new places ---

XSS = "<script>alert(1)</script>"
XSS_ESCAPED = "&lt;script&gt;alert(1)&lt;/script&gt;"


@pytest.mark.parametrize("page", ["", "/edit", "/delete"])
def test_html_in_title_and_outcome_is_escaped_on_every_page(client, app, page):
    topic_id = add(app, XSS, outcome="<b>x</b>")

    html = client.get(f"/topics/{topic_id}{page}").get_data(as_text=True)

    assert XSS_ESCAPED in html
    assert "<script>alert(1)" not in html
    if page != "/delete":
        assert "&lt;b&gt;x&lt;/b&gt;" in html
        assert "<b>x</b>" not in html


def test_multiline_outcome_keeps_line_breaks_without_html(client, app):
    topic_id = add(app, outcome="א\nב")

    html = client.get(f"/topics/{topic_id}").get_data(as_text=True)

    assert "א\nב" in html
    assert "<br" not in html
