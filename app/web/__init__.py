import os

from flask import Flask

from app.storage.db import DEFAULT_DATABASE_URL, get_engine


def create_app(database_url=None):
    app = Flask(__name__)
    url = database_url or os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL)
    app.config["ENGINE"] = get_engine(url)

    from app.web.routes import bp

    app.register_blueprint(bp)
    return app
