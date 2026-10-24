import re
from datetime import date, datetime, timedelta, timezone

import pytest

from app.core.deadlines import israel_date
from app.storage.repository import (
    THREAD,
    USER_SUMMARY,
    add_topic,
    add_update,
    get_topic,
    get_update,
    list_topics,
    list_updates,
)
from app.web import create_app

TODAY = date(2026, 10, 18)


@pytest.fixture
def app(db_url, monkeypatch):
    monkeypatch.setattr("app.web.routes.today_in_israel", lambda: TODAY)
    app = create_app(db_url)
    app.config["WTF_CSRF_ENABLED"] = False  # the CSRF tests below use csrf_app instead
    return app


@pytest.fixture
def csrf_app(db_url, monkeypatch):
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
    [(2, "בעוד יומיים"), (-1, "לפני יום"), (-2, "לפני יומיים"), (10, "בעוד 10 ימים")],
)
def test_days_text_rendered_in_page(client, offset, text):
    post(client, "x", (TODAY + timedelta(days=offset)).isoformat())

    assert f'<bdi class="days">{text}</bdi>' in client.get("/").get_data(as_text=True)


@pytest.mark.parametrize("offset, label", [(0, "היום"), (1, "מחר")])
def test_days_text_hidden_for_today_and_tomorrow_but_badge_stays(client, offset, label):
    post(client, "x", (TODAY + timedelta(days=offset)).isoformat())

    html = client.get("/").get_data(as_text=True)

    assert 'class="days"' not in html
    assert f'<span class="badge">{label}</span>' in html
    assert '<bdi class="due">' in html


@pytest.mark.parametrize("offset, label", [(0, "היום"), (1, "מחר")])
def test_detail_hides_days_text_for_today_and_tomorrow(client, app, offset, label):
    topic_id = add(app, due=(TODAY + timedelta(days=offset)).isoformat())

    html = client.get(f"/topics/{topic_id}").get_data(as_text=True)

    assert 'class="days"' not in html
    assert f'<span class="badge">{label}</span>' in html


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


# --- CSRF protection (csrf_app has the protection on) ---

TOKEN_RE = re.compile(r'name="csrf_token" value="([^"]+)"')


def token_from(client, path):
    html = client.get(path).get_data(as_text=True)
    match = TOKEN_RE.search(html)
    assert match, f"no csrf_token field on {path}"
    return match.group(1)


def form_data(token, title="נושא", outcome=OUTCOME):
    return {"title": title, "due_date": "2026-10-28", "required_outcome": outcome, "csrf_token": token}


@pytest.mark.parametrize("path", ["/", "/topics/{id}/edit", "/topics/{id}/delete"])
def test_every_form_has_a_csrf_token_field(csrf_app, path):
    topic_id = add(csrf_app)

    assert token_from(csrf_app.test_client(), path.format(id=topic_id))


@pytest.mark.parametrize("path", ["/", "/topics/{id}/edit", "/topics/{id}/delete"])
@pytest.mark.parametrize("token", [None, "", "not-a-real-token"])
def test_post_without_valid_token_is_rejected_and_changes_nothing(csrf_app, path, token):
    topic_id = add(csrf_app, "מקורי")
    data = form_data(token) if token is not None else {k: v for k, v in form_data("x").items() if k != "csrf_token"}

    resp = csrf_app.test_client().post(path.format(id=topic_id), data=data)

    assert resp.status_code == 400
    assert "הטופס פג תוקף או שאינו תקין" in resp.get_data(as_text=True)
    assert [t["title"] for t in list_topics(csrf_app.config["ENGINE"])] == ["מקורי"]


def test_token_from_another_session_is_rejected(csrf_app):
    topic_id = add(csrf_app)
    stolen = token_from(csrf_app.test_client(), f"/topics/{topic_id}/delete")

    resp = csrf_app.test_client().post(f"/topics/{topic_id}/delete", data={"csrf_token": stolen})

    assert resp.status_code == 400
    assert get_topic(csrf_app.config["ENGINE"], topic_id) is not None


def test_create_with_valid_token(csrf_app):
    client = csrf_app.test_client()

    resp = client.post("/", data=form_data(token_from(client, "/"), "חדש"))

    assert resp.status_code == 303
    assert [t["title"] for t in list_topics(csrf_app.config["ENGINE"])] == ["חדש"]


def test_edit_with_valid_token(csrf_app):
    topic_id = add(csrf_app, "ישן")
    client = csrf_app.test_client()

    resp = client.post(f"/topics/{topic_id}/edit", data=form_data(token_from(client, f"/topics/{topic_id}/edit"), "חדש"))

    assert resp.status_code == 303
    assert get_topic(csrf_app.config["ENGINE"], topic_id)["title"] == "חדש"


def test_delete_with_valid_token(csrf_app):
    topic_id = add(csrf_app)
    client = csrf_app.test_client()

    resp = client.post(f"/topics/{topic_id}/delete", data={"csrf_token": token_from(client, f"/topics/{topic_id}/delete")})

    assert resp.status_code == 303
    assert get_topic(csrf_app.config["ENGINE"], topic_id) is None


def test_get_delete_confirmation_needs_no_token_and_deletes_nothing(csrf_app):
    topic_id = add(csrf_app)

    assert csrf_app.test_client().get(f"/topics/{topic_id}/delete").status_code == 200
    assert get_topic(csrf_app.config["ENGINE"], topic_id) is not None


def test_session_cookie_is_samesite_lax_and_httponly(csrf_app):
    cookie = csrf_app.test_client().get("/").headers.get("Set-Cookie", "")

    assert "SameSite=Lax" in cookie
    assert "HttpOnly" in cookie


def test_app_refuses_to_start_without_secret_key(db_url, monkeypatch):
    monkeypatch.delenv("SECRET_KEY")
    monkeypatch.setattr("app.web.load_dotenv", lambda: None)  # do not read the real .env

    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        create_app(db_url)


# --- the whole list card is the link ---


def test_each_list_card_has_a_chevron_and_exactly_one_link_to_its_topic(client, app):
    first, second = add(app, "ראשון"), add(app, "שני")

    html = client.get("/").get_data(as_text=True)
    cards = html.split('<li class="')[1:]

    assert len(cards) == 2
    for card, topic_id in zip(cards, (first, second)):
        assert card.count("<a ") == 1
        assert f'<a class="title" href="/topics/{topic_id}">' in card
        assert 'class="chev"' in card and 'aria-hidden="true"' in card


# --- update history (stage 4) ---


def post_update(client, topic_id, kind=THREAD, content="עדכון", entry="2026-10-17"):
    data = {"content": content, "entry_date": entry}
    if kind is not None:
        data["kind"] = kind
    return client.post(f"/topics/{topic_id}/updates", data=data)


def updates_of(app, topic_id):
    return list_updates(app.config["ENGINE"], topic_id)


def test_detail_without_updates_shows_empty_message_and_collapsed_form(client, app):
    topic_id = add(app)

    html = client.get(f"/topics/{topic_id}").get_data(as_text=True)

    assert "היסטוריית עדכונים" in html
    assert "אין עדכונים עדיין" in html
    assert '<details class="add-update">' in html


def test_form_has_two_unchecked_radios_with_required_labels_and_today_as_default_date(client, app):
    topic_id = add(app)

    html = client.get(f"/topics/{topic_id}").get_data(as_text=True)

    assert "ציטוט מהתכתבות" in html and "סיכום שיחה או פגישה" in html
    assert "checked" not in html
    assert 'name="entry_date" value="2026-10-18"' in html
    assert 'max="2026-10-18"' in html
    assert 'name="channel"' not in html


def test_add_update_redirects_and_it_is_listed(client, app):
    topic_id = add(app)

    resp = post_update(client, topic_id, THREAD, "הספק אישר")

    assert resp.status_code == 303
    assert resp.headers["Location"].endswith(f"/topics/{topic_id}")
    assert "הספק אישר" in client.get(f"/topics/{topic_id}").get_data(as_text=True)


def test_two_updates_are_listed_newest_first(client, app):
    topic_id = add(app)
    post_update(client, topic_id, THREAD, "ישן יותר", "2026-10-10")
    post_update(client, topic_id, THREAD, "חדש יותר", "2026-10-12")

    html = client.get(f"/topics/{topic_id}").get_data(as_text=True)

    assert html.index("חדש יותר") < html.index("ישן יותר")
    assert len(updates_of(app, topic_id)) == 2


def test_update_of_one_topic_does_not_appear_on_another(client, app):
    first, second = add(app, "ראשון"), add(app, "שני")
    post_update(client, first, THREAD, "רק בראשון")

    assert "רק בראשון" not in client.get(f"/topics/{second}").get_data(as_text=True)


@pytest.mark.parametrize("kind", [None, "", "manual", "summary"])
def test_invalid_or_missing_kind_is_rejected_and_text_kept(client, app, kind):
    topic_id = add(app)

    resp = post_update(client, topic_id, kind, "הטקסט שנשאר")
    html = resp.get_data(as_text=True)

    assert resp.status_code == 400
    assert "יש לבחור סוג עדכון" in html
    assert "הטקסט שנשאר" in html
    assert '<details class="add-update" open>' in html
    assert updates_of(app, topic_id) == []


@pytest.mark.parametrize("content", ["", "   ", "\n \t"])
def test_blank_content_is_rejected(client, app, content):
    topic_id = add(app)

    resp = post_update(client, topic_id, THREAD, content)

    assert resp.status_code == 400
    assert "יש להזין את תוכן העדכון" in resp.get_data(as_text=True)
    assert updates_of(app, topic_id) == []


def test_future_date_is_rejected_and_today_is_accepted(client, app):
    topic_id = add(app)

    future = post_update(client, topic_id, THREAD, "עתידי", "2026-10-19")
    today = post_update(client, topic_id, THREAD, "היום", "2026-10-18")

    assert future.status_code == 400 and "אי אפשר להזין תאריך עתידי" in future.get_data(as_text=True)
    assert today.status_code == 303
    assert [u["content"] for u in updates_of(app, topic_id)] == ["היום"]


@pytest.mark.parametrize("entry", ["", "2026-02-30", "abc"])
def test_invalid_entry_date_is_rejected(client, app, entry):
    topic_id = add(app)

    resp = post_update(client, topic_id, THREAD, "טקסט", entry)

    assert resp.status_code == 400
    assert "יש להזין תאריך תקין" in resp.get_data(as_text=True)
    assert updates_of(app, topic_id) == []


@pytest.mark.parametrize("kind, limit", [(THREAD, 50000), (USER_SUMMARY, 5000)])
def test_length_limit_through_the_page(client, app, kind, limit):
    topic_id = add(app)

    ok = post_update(client, topic_id, kind, "א" * limit)
    too_long = post_update(client, topic_id, kind, "ב" * (limit + 1))
    html = too_long.get_data(as_text=True)

    assert ok.status_code == 303
    assert too_long.status_code == 400
    assert f"{limit + 1:,} תווים" in html and f"המותר הוא {limit:,}" in html
    assert "לפצל לשני עדכונים" in html
    assert "ב" * (limit + 1) in html  # the pasted text stays in the form
    assert "maxlength" not in html.split('name="content"')[1].split(">")[0]
    assert len(updates_of(app, topic_id)) == 1


def test_oversized_request_is_413_in_hebrew_and_saves_nothing(client, app):
    topic_id = add(app)

    resp = post_update(client, topic_id, THREAD, "א" * (3 * 1024 * 1024))

    assert resp.status_code == 413
    assert "הבקשה גדולה מדי" in resp.get_data(as_text=True)
    assert updates_of(app, topic_id) == []


def test_html_in_update_is_shown_as_text_everywhere(client, app):
    topic_id = add(app)
    post_update(client, topic_id, THREAD, "<script>alert(1)</script> <b>x</b>")
    post_update(client, topic_id, USER_SUMMARY, "<img src=x onerror=alert(2)>")
    update_id = updates_of(app, topic_id)[0]["id"]

    for path in (f"/topics/{topic_id}", f"/topics/{topic_id}/updates/{update_id}/delete"):
        html = client.get(path).get_data(as_text=True)
        assert "<script>alert(1)</script>" not in html
        assert "<img src=x" not in html
    detail = client.get(f"/topics/{topic_id}").get_data(as_text=True)
    assert "&lt;script&gt;alert(1)&lt;/script&gt; &lt;b&gt;x&lt;/b&gt;" in detail


def test_rejected_form_escapes_the_kept_text(client, app):
    topic_id = add(app)

    html = post_update(client, topic_id, None, "<script>x</script>").get_data(as_text=True)

    assert "<script>x</script>" not in html and "&lt;script&gt;x&lt;/script&gt;" in html


def test_summary_is_marked_with_the_word_and_thread_is_not(client, app):
    topic_id = add(app)
    post_update(client, topic_id, THREAD, "התכתבות")
    post_update(client, topic_id, USER_SUMMARY, "סיכום של שיחה")

    html = client.get(f"/topics/{topic_id}").get_data(as_text=True)
    thread_item, summary_item = sorted(html.split('<li class="update')[1:], key=lambda item: "סיכום של שיחה" in item)

    assert '<span class="update-kind">סיכום</span>' in summary_item
    assert "update-kind" not in thread_item
    assert 'class="update thread"' in html and html.count("update-kind") == 1
    assert "שהזנתי" not in html and "לא ציטוט" not in html


def test_short_update_is_shown_in_full_without_fold(client, app):
    topic_id = add(app)
    post_update(client, topic_id, THREAD, "ש\n" * 7 + "ח")

    html = client.get(f"/topics/{topic_id}").get_data(as_text=True)

    assert "הצגת הטקסט המלא" not in html


@pytest.mark.parametrize("content", ["א" * 501, "\n".join(["ש"] * 9)])
def test_long_update_is_folded_with_the_full_text_inside_details(client, app, content):
    topic_id = add(app)
    post_update(client, topic_id, THREAD, content)

    html = client.get(f"/topics/{topic_id}").get_data(as_text=True)

    assert "<details>" in html and "הצגת הטקסט המלא" in html
    assert content in html  # the full text is in the page, inside the fold


def test_line_breaks_are_kept_with_pre_wrap_and_no_extra_html(client, app):
    topic_id = add(app)
    post_update(client, topic_id, THREAD, "שורה א\r\nשורה ב")

    html = client.get(f"/topics/{topic_id}").get_data(as_text=True)

    assert "שורה א\nשורה ב" in html and "<br" not in html
    assert "white-space: pre-wrap" in client.get("/static/style.css").get_data(as_text=True)


def test_entered_on_is_shown_only_when_it_differs_from_the_entry_date(client, app):
    topic_id = add(app)
    engine = app.config["ENGINE"]
    entered_today = israel_date(datetime.now(timezone.utc))
    add_update(engine, topic_id, THREAD, "הוזן באותו יום", entered_today)
    add_update(engine, topic_id, THREAD, "הוזן באיחור", date(2026, 10, 1))

    items = client.get(f"/topics/{topic_id}").get_data(as_text=True).split('<li class="update')[1:]
    same, late = sorted(items, key=lambda item: "הוזן באיחור" in item)

    assert "הוזן ב-" not in same
    assert f"הוזן ב-<bdi>{entered_today.strftime('%d.%m.%Y')}</bdi>" in late


def test_delete_update_confirm_page_does_not_delete(client, app):
    topic_id = add(app)
    post_update(client, topic_id, THREAD, "יישאר")
    update_id = updates_of(app, topic_id)[0]["id"]

    resp = client.get(f"/topics/{topic_id}/updates/{update_id}/delete")

    assert resp.status_code == 200 and "אי אפשר לבטל" in resp.get_data(as_text=True)
    assert len(updates_of(app, topic_id)) == 1


def test_delete_update_removes_only_that_one(client, app):
    topic_id = add(app)
    post_update(client, topic_id, THREAD, "יישאר", "2026-10-10")
    post_update(client, topic_id, THREAD, "יימחק", "2026-10-12")
    gone = updates_of(app, topic_id)[0]["id"]

    resp = client.post(f"/topics/{topic_id}/updates/{gone}/delete")

    assert resp.status_code == 303
    assert [u["content"] for u in updates_of(app, topic_id)] == ["יישאר"]


def test_delete_update_is_post_only(client, app):
    topic_id = add(app)
    post_update(client, topic_id, THREAD, "יישאר")
    update_id = updates_of(app, topic_id)[0]["id"]

    for method in ("put", "delete", "patch"):
        assert getattr(client, method)(f"/topics/{topic_id}/updates/{update_id}/delete").status_code == 405
    assert len(updates_of(app, topic_id)) == 1


def test_there_is_no_way_to_edit_an_update(client, app):
    topic_id = add(app)
    post_update(client, topic_id, THREAD, "מקורי")
    update_id = updates_of(app, topic_id)[0]["id"]

    for path in (f"/topics/{topic_id}/updates/{update_id}", f"/topics/{topic_id}/updates/{update_id}/edit"):
        assert client.get(path).status_code == 404
        assert client.post(path, data={"content": "שונה"}).status_code in (404, 405)
    assert updates_of(app, topic_id)[0]["content"] == "מקורי"


def test_update_of_another_topic_or_missing_id_is_404(client, app):
    first, second = add(app, "ראשון"), add(app, "שני")
    post_update(client, first, THREAD, "של הראשון")
    update_id = updates_of(app, first)[0]["id"]

    for path in (f"/topics/{second}/updates/{update_id}/delete", f"/topics/{first}/updates/999/delete"):
        assert client.get(path).status_code == 404
        assert client.post(path).status_code == 404
    assert len(updates_of(app, first)) == 1


def test_adding_an_update_to_a_missing_topic_is_404(client, app):
    assert post_update(client, 999).status_code == 404


def test_deleting_a_topic_deletes_its_updates(client, app):
    first, second = add(app, "ראשון"), add(app, "שני")
    post_update(client, first, THREAD, "יימחק")
    post_update(client, second, THREAD, "יישאר")
    update_id = updates_of(app, first)[0]["id"]

    client.post(f"/topics/{first}/delete")

    assert get_update(app.config["ENGINE"], update_id) is None
    assert len(updates_of(app, second)) == 1


@pytest.mark.parametrize("path", ["/topics/{id}", "/topics/{id}/updates/{uid}/delete"])
def test_update_forms_have_a_csrf_token_field(csrf_app, path):
    topic_id = add(csrf_app)
    uid = add_update(csrf_app.config["ENGINE"], topic_id, THREAD, "עדכון", date(2026, 10, 10))

    assert token_from(csrf_app.test_client(), path.format(id=topic_id, uid=uid))


@pytest.mark.parametrize("token", [None, "", "not-a-real-token"])
def test_adding_and_deleting_an_update_without_a_valid_token_is_rejected(csrf_app, token):
    topic_id = add(csrf_app)
    uid = add_update(csrf_app.config["ENGINE"], topic_id, THREAD, "עדכון", date(2026, 10, 10))
    data = {"kind": THREAD, "content": "חדש", "entry_date": "2026-10-17"}
    if token is not None:
        data["csrf_token"] = token

    add_resp = csrf_app.test_client().post(f"/topics/{topic_id}/updates", data=data)
    del_resp = csrf_app.test_client().post(f"/topics/{topic_id}/updates/{uid}/delete", data=data)

    assert add_resp.status_code == del_resp.status_code == 400
    assert [u["content"] for u in list_updates(csrf_app.config["ENGINE"], topic_id)] == ["עדכון"]


def test_adding_and_deleting_an_update_with_a_valid_token(csrf_app):
    topic_id = add(csrf_app)
    client = csrf_app.test_client()
    token = token_from(client, f"/topics/{topic_id}")

    added = client.post(
        f"/topics/{topic_id}/updates",
        data={"kind": USER_SUMMARY, "content": "סיכום", "entry_date": "2026-10-17", "csrf_token": token},
    )
    uid = list_updates(csrf_app.config["ENGINE"], topic_id)[0]["id"]
    deleted = client.post(f"/topics/{topic_id}/updates/{uid}/delete", data={"csrf_token": token})

    assert added.status_code == deleted.status_code == 303
    assert list_updates(csrf_app.config["ENGINE"], topic_id) == []
