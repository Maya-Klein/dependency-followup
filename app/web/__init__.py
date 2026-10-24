import os

from dotenv import load_dotenv
from flask import Flask
from flask_wtf.csrf import CSRFProtect

from app.storage.db import DEFAULT_DATABASE_URL, get_engine

csrf = CSRFProtect()


def create_app(database_url=None):
    load_dotenv()  # reads .env if present; variables already set are not overridden

    app = Flask(__name__)
    url = database_url or os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL)
    app.config["ENGINE"] = get_engine(url)

    secret_key = os.environ.get("SECRET_KEY")
    if not secret_key:
        raise RuntimeError("SECRET_KEY is not set: copy .env.example to .env and set a value")
    app.config["SECRET_KEY"] = secret_key
    app.config["MAX_CONTENT_LENGTH"] = 2 * 1024 * 1024  # a pasted thread is at most 50,000 characters; refuse far more
    app.config["WTF_CSRF_TIME_LIMIT"] = None  # token lives as long as the session
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    csrf.init_app(app)

    from app.web.routes import bp

    app.register_blueprint(bp)
    return app
