"""Security headers (CSP and friends) on every kind of response, and templates that need nothing more than 'self'."""
from datetime import date
from pathlib import Path

import pytest

from app.storage.repository import add_topic
from app.web import SECURITY_HEADERS, create_app

WEB_DIR = Path(__file__).resolve().parent.parent / "app" / "web"
TEMPLATES = sorted((WEB_DIR / "templates").glob("*.html"))
CSP = "default-src 'self'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'"


@pytest.fixture
def app(db_url, monkeypatch):
    monkeypatch.setattr("app.web.routes.today_in_israel", lambda: date(2026, 10, 18))
    app = create_app(db_url)
    app.config["WTF_CSRF_ENABLED"] = False
    return app


@pytest.fixture
def csrf_app(db_url, monkeypatch):
    monkeypatch.setattr("app.web.routes.today_in_israel", lambda: date(2026, 10, 18))
    return create_app(db_url)


def assert_security_headers(resp):
    assert resp.headers.get("Content-Security-Policy") == CSP
    assert resp.headers.get("X-Content-Type-Options") == "nosniff"
    assert resp.headers.get("Referrer-Policy") == "same-origin"


def test_the_policy_is_the_planned_one():
    assert SECURITY_HEADERS["Content-Security-Policy"] == CSP


def test_headers_on_a_page(app):
    resp = app.test_client().get("/")

    assert resp.status_code == 200
    assert_security_headers(resp)


def test_headers_on_a_topic_page(app):
    topic_id = add_topic(app.config["ENGINE"], "נושא", date(2026, 10, 28), "אישור")

    resp = app.test_client().get(f"/topics/{topic_id}")

    assert resp.status_code == 200
    assert_security_headers(resp)


def test_headers_on_a_redirect(app):
    resp = app.test_client().post("/", data={"title": "נושא", "due_date": "2026-10-28", "required_outcome": "אישור"})

    assert resp.status_code == 303
    assert_security_headers(resp)


def test_headers_on_404(app):
    resp = app.test_client().get("/topics/999999")

    assert resp.status_code == 404
    assert_security_headers(resp)


def test_headers_on_csrf_400(csrf_app):
    resp = csrf_app.test_client().post("/", data={"title": "נושא", "due_date": "2026-10-28", "required_outcome": "אישור"})

    assert resp.status_code == 400
    assert_security_headers(resp)


def test_headers_on_413(app):
    resp = app.test_client().post("/", data={"title": "x" * (5 * 1024 * 1024)})

    assert resp.status_code == 413
    assert_security_headers(resp)


@pytest.mark.parametrize("path", ["/static/style.css", "/static/fonts/rubik-hebrew.woff2"])
def test_headers_on_a_static_file(app, path):
    resp = app.test_client().get(path)

    assert resp.status_code == 200
    assert_security_headers(resp)
    resp.close()


def test_there_are_templates_to_check():
    assert len(TEMPLATES) >= 5


@pytest.mark.parametrize("template", TEMPLATES, ids=lambda p: p.name)
def test_template_needs_nothing_beyond_self(template):
    # Inline style and script would be blocked by the CSP, and so would anything loaded from another site.
    text = template.read_text(encoding="utf-8").lower()

    assert "style=" not in text
    assert "<script" not in text
    assert "http" not in text


def test_stylesheet_loads_nothing_from_outside():
    text = (WEB_DIR / "static" / "style.css").read_text(encoding="utf-8").lower()

    assert "http" not in text
    assert "@import" not in text
