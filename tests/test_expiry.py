"""Tests for the expiry housekeeping logic (via /api/list and directly)."""

import base64
import time
import psycopg2
import pytest

from tests.conftest import TEST_DB
from app.expiry import run_expiry


GOOD_AUTH = {"Authorization": "Basic " + base64.b64encode(b"edl:edlpass").decode()}


def _insert_with_offset(list_name, ip, seconds_from_now):
    """Insert an entry expiring `seconds_from_now` seconds from now (negative = past)."""
    conn = psycopg2.connect(**TEST_DB)
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO blocklist_entries (list_name, ip, reason, added_by, expires_at)
            VALUES (%s, %s::inet, 'test', 'system',
                    NOW() + (%s || ' seconds')::interval)
            """,
            (list_name, ip, str(seconds_from_now)),
        )
    conn.commit()
    conn.close()


def _active_ips(list_name):
    conn = psycopg2.connect(**TEST_DB)
    with conn.cursor() as cur:
        cur.execute("SELECT host(ip) AS ip FROM blocklist_entries WHERE list_name = %s", (list_name,))
        ips = {r[0] for r in cur.fetchall()}
    conn.close()
    return ips


def _audit_count(ip, action):
    conn = psycopg2.connect(**TEST_DB)
    with conn.cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) FROM audit_logs WHERE ip = %s::inet AND action = %s",
            (ip, action),
        )
        n = cur.fetchone()[0]
    conn.close()
    return n


class TestRunExpiry:
    """Direct unit tests for run_expiry()."""

    def test_does_nothing_when_no_expired(self, app):
        _insert_with_offset("default", "1.0.0.1", +3600)
        with app.app_context():
            count = run_expiry("default")
        assert count == 0
        assert "1.0.0.1" in _active_ips("default")

    def test_removes_expired_entry(self, app):
        _insert_with_offset("default", "1.0.0.2", -1)
        with app.app_context():
            count = run_expiry("default")
        assert count == 1
        assert "1.0.0.2" not in _active_ips("default")

    def test_audit_row_created_for_expired(self, app):
        _insert_with_offset("default", "1.0.0.3", -1)
        with app.app_context():
            run_expiry("default")
        assert _audit_count("1.0.0.3", "expire") == 1

    def test_idempotent_second_call(self, app):
        _insert_with_offset("default", "1.0.0.4", -1)
        with app.app_context():
            run_expiry("default")
            count2 = run_expiry("default")
        assert count2 == 0
        # Audit should have exactly 1 expire row, not 2
        assert _audit_count("1.0.0.4", "expire") == 1

    def test_only_affects_target_list(self, app):
        _insert_with_offset("default", "1.0.0.5", -1)
        _insert_with_offset("inbound", "1.0.0.5", -1)
        with app.app_context():
            run_expiry("default")
        assert "1.0.0.5" not in _active_ips("default")
        assert "1.0.0.5" in _active_ips("inbound")

    def test_valid_entries_untouched(self, app):
        _insert_with_offset("default", "1.0.0.6", -1)
        _insert_with_offset("default", "1.0.0.7", +3600)
        with app.app_context():
            run_expiry("default")
        assert "1.0.0.6" not in _active_ips("default")
        assert "1.0.0.7" in _active_ips("default")


class TestExpiryViaListEndpoint:
    """Expiry triggered by GET /api/list."""

    def test_expired_entry_cleaned_on_list_request(self, client):
        _insert_with_offset("default", "2.0.0.1", -1)
        client.get("/api/list?id=default", headers=GOOD_AUTH)
        assert "2.0.0.1" not in _active_ips("default")

    def test_expired_entry_not_in_response(self, client):
        _insert_with_offset("default", "2.0.0.2", -1)
        r = client.get("/api/list?id=default", headers=GOOD_AUTH)
        assert "2.0.0.2" not in r.data.decode()

    def test_multiple_expired_all_removed(self, client):
        for i in range(5):
            _insert_with_offset("default", f"2.0.1.{i}", -1)
        r = client.get("/api/list?id=default", headers=GOOD_AUTH)
        assert r.data.strip() == b""
        assert _active_ips("default") == set()
