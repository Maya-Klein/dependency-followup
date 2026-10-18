from datetime import date, timedelta

import pytest

from app.storage.repository import list_topics
from app.web import create_app

TODAY = date(2026, 10, 18)


@pytest.fixture
def app(db_url, monkeypatch):
    monkeypatch.setattr("app.web.routes.today_in_israel", lambda: TODAY)
    return create_app(db_url)


@pytest.fixture
def client(app):
    return app.test_client()


def post(client, title, due):
    return client.post("/", data={"title": title, "due_date": due})


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
    [(1, "בעוד יום אחד"), (2, "בעוד יומיים"), (0, "היום"), (-1, "לפני יום אחד"), (-2, "לפני יומיים")],
)
def test_days_text_rendered_in_page(client, offset, text):
    post(client, "x", (TODAY + timedelta(days=offset)).isoformat())

    assert f'<bdi class="days">{text}</bdi>' in client.get("/").get_data(as_text=True)


@pytest.mark.parametrize(
    "offset, level, label",
    [
        (10, "far", "רחוק"),
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
