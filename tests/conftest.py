"""
Pytest fixtures for the blocklist application.

Database strategy
-----------------
Tests expect a running PostgreSQL reachable via TEST_DB_* env vars
(defaulting to localhost:5432, db=test_blocklist, user/pass=postgres).
The `db_session` fixture (session-scoped) creates the test DB + runs
migrations once.  Each test gets a clean slate via table truncation.

OIDC strategy
-------------
OIDC is bypassed entirely: fixtures pre-seed Flask sessions with a
valid `user` dict and a known CSRF token.  The `require_session` and
`require_csrf` decorators only inspect the session, so no real IdP is
required.
"""

import os
import secrets

import psycopg2
import pytest

from app import create_app

# ---------------------------------------------------------------------------
# Test DB config (overridable via env vars)
# ---------------------------------------------------------------------------
TEST_DB = {
    "host":     os.environ.get("TEST_DB_HOST",     "localhost"),
    "port":     int(os.environ.get("TEST_DB_PORT", 5432)),
    "dbname":   os.environ.get("TEST_DB_NAME",     "test_blocklist"),
    "user":     os.environ.get("TEST_DB_USER",     "postgres"),
    "password": os.environ.get("TEST_DB_PASSWORD", "postgres"),
}

# Super-user DSN used to CREATE / DROP the test database
ADMIN_DB = {**TEST_DB, "dbname": "postgres"}

CSRF = "test-csrf-token"
USER = {"email": "tester@example.com", "name": "Tester"}


# ---------------------------------------------------------------------------
# Session-scoped: create DB, run migrations, drop on teardown
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session")
def db_session():
    """Create the test database and apply migrations."""
    admin = psycopg2.connect(**ADMIN_DB)
    admin.autocommit = True
    with admin.cursor() as cur:
        cur.execute(f"DROP DATABASE IF EXISTS {TEST_DB['dbname']}")
        cur.execute(f"CREATE DATABASE {TEST_DB['dbname']}")
    admin.close()

    # Apply migration
    conn = psycopg2.connect(**TEST_DB)
    migration = (
        os.path.dirname(__file__) + "/../migrations/001_init.sql"
    )
    with open(migration) as f:
        sql = f.read()
    with conn.cursor() as cur:
        cur.execute(sql)
    conn.commit()
    conn.close()

    yield TEST_DB

    # Teardown
    admin = psycopg2.connect(**ADMIN_DB)
    admin.autocommit = True
    with admin.cursor() as cur:
        # Terminate connections so DROP works
        cur.execute(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
            "WHERE datname = %s AND pid <> pg_backend_pid()",
            (TEST_DB["dbname"],),
        )
        cur.execute(f"DROP DATABASE IF EXISTS {TEST_DB['dbname']}")
    admin.close()


# ---------------------------------------------------------------------------
# Function-scoped: truncate tables before each test
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def clean_tables(db_session):
    conn = psycopg2.connect(**db_session)
    with conn.cursor() as cur:
        cur.execute("TRUNCATE blocklist_entries, audit_logs RESTART IDENTITY CASCADE")
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Application + test client
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session")
def app(db_session):
    cfg = {
        "TESTING": True,
        "SECRET_KEY": "test-secret",
        "SESSION_COOKIE_SECURE": False,
        # Point the app at the test DB
        **{k.upper(): v for k, v in {
            "db_host":     db_session["host"],
            "db_port":     str(db_session["port"]),
            "db_name":     db_session["dbname"],
            "db_user":     db_session["user"],
            "db_password": db_session["password"],
        }.items()},
    }

    # Inject DB env vars so db.py can read them
    os.environ.update({
        "DB_HOST":     db_session["host"],
        "DB_PORT":     str(db_session["port"]),
        "DB_NAME":     db_session["dbname"],
        "DB_USER":     db_session["user"],
        "DB_PASSWORD": db_session["password"],
        "SESSION_SECRET":            "test-secret",
        "LIST_BASIC_AUTH_USER":      "edl",
        "LIST_BASIC_AUTH_PASSWORD":  "edlpass",
        "DEFAULT_LIST":              "default",
        "OIDC_ISSUER":        "https://idp.test",
        "OIDC_CLIENT_ID":     "test-client",
        "OIDC_CLIENT_SECRET": "test-secret",
        "OIDC_AUTH_ENDPOINT": "https://idp.test/auth",
        "OIDC_TOKEN_ENDPOINT":"https://idp.test/token",
        "OIDC_JWKS_URI":      "https://idp.test/jwks",
        "OIDC_REDIRECT_URI":  "https://app.test/auth/callback",
    })

    application = create_app(cfg)
    application.config["SESSION_COOKIE_SECURE"] = False
    return application


@pytest.fixture
def client(app):
    return app.test_client()


# ---------------------------------------------------------------------------
# Authenticated client helpers
# ---------------------------------------------------------------------------
@pytest.fixture
def auth_client(client, app):
    """A test client with a pre-seeded authenticated session."""
    with client.session_transaction() as sess:
        sess["user"] = USER
        sess["csrf_token"] = CSRF
    return client


@pytest.fixture
def csrf_headers():
    return {"X-CSRF-Token": CSRF, "Content-Type": "application/json"}
