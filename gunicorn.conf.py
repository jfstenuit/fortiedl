"""Gunicorn configuration."""

import os

bind = f"0.0.0.0:{os.environ.get('APP_PORT', '8080')}"
workers = int(os.environ.get("GUNICORN_WORKERS", "2"))
worker_class = "sync"
timeout = 30
keepalive = 5
accesslog = "-"
errorlog = "-"
loglevel = os.environ.get("APP_LOG_LEVEL", "info").lower()
