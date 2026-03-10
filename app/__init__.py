"""Flask application factory."""

import os
import logging
import logging.handlers

from flask import Flask, session, redirect
from flask import send_from_directory


def create_app(config: dict | None = None) -> Flask:
    app = Flask(__name__, static_folder="../static", static_url_path="/static")

    # -----------------------------------------------------------------------
    # Core config
    # -----------------------------------------------------------------------
    app.config["SECRET_KEY"] = os.environ.get("SESSION_SECRET", "dev-secret-CHANGE-ME")
    app.config["SESSION_COOKIE_SECURE"] = True
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["PERMANENT_SESSION_LIFETIME"] = 3600  # seconds

    if config:
        app.config.update(config)

    # -----------------------------------------------------------------------
    # Logging
    # -----------------------------------------------------------------------
    _setup_logging(app)

    # -----------------------------------------------------------------------
    # Database
    # -----------------------------------------------------------------------
    from .db import init_db
    init_db(app)

    # -----------------------------------------------------------------------
    # Blueprints
    # -----------------------------------------------------------------------
    from .auth import auth_bp
    from .routes.list_api import list_api_bp
    from .routes.entries import entries_bp
    from .routes.audit import audit_bp

    for bp in (auth_bp, list_api_bp, entries_bp, audit_bp):
        app.register_blueprint(bp)

    # -----------------------------------------------------------------------
    # Root route
    # -----------------------------------------------------------------------
    @app.route("/")
    def index():
        if "user" not in session:
            return redirect("/auth/login")
        return send_from_directory(app.static_folder, "index.html")

    # -----------------------------------------------------------------------
    # JSON error responses for API paths
    # -----------------------------------------------------------------------
    from flask import jsonify

    @app.errorhandler(400)
    @app.errorhandler(401)
    @app.errorhandler(403)
    @app.errorhandler(404)
    @app.errorhandler(409)
    @app.errorhandler(500)
    def json_error(exc):
        from werkzeug.exceptions import HTTPException
        code = exc.code if isinstance(exc, HTTPException) else 500
        desc = exc.description if isinstance(exc, HTTPException) else "Internal server error"
        return jsonify({"error": desc}), code

    return app


def _setup_logging(app: Flask) -> None:
    level_name = os.environ.get("APP_LOG_LEVEL", "INFO")
    level = getattr(logging, level_name, logging.INFO)
    app.logger.setLevel(level)

    if not app.logger.handlers:
        ch = logging.StreamHandler()
        ch.setLevel(level)
        ch.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
        app.logger.addHandler(ch)

    # Forward to syslog if available (container has /dev/log)
    try:
        sh = logging.handlers.SysLogHandler(address="/dev/log")
        sh.setLevel(level)
        sh.setFormatter(logging.Formatter("blocklist[%(process)d]: %(levelname)s %(message)s"))
        app.logger.addHandler(sh)
    except (OSError, AttributeError):
        pass
