"""Tests for GET /api/list (Basic Auth, EDL endpoint)."""

import base64
import psycopg2
import pytest

from tests.conftest import TEST_DB, USER


def b64(user, pw):
    return "Basic " + base64.b64encode(f"{user}:{pw}".encode()).decode()


GOOD_AUTH = {"Authorization": b64("edl", "edlpass")}
BAD_AUTH  = {"Authorization": b64("wrong", "creds")}


def _insert_entry(list_name, ip, reason="test", expires_in="1w"):
    """Directly insert an entry into the DB."""
    conn = psycopg2.connect(**TEST_DB)
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO blocklist_entries (list_name, ip, reason, added_by, expires_at)
            VALUES (%s, %s::inet, %s, 'tester@example.com',
                    NOW() + INTERVAL '7 days')
            """,
            (list_name, ip, reason),
        )
    conn.commit()
    conn.close()


def _insert_expired(list_name, ip):
    conn = psycopg2.connect(**TEST_DB)
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO blocklist_entries (list_name, ip, reason, added_by, expires_at)
            VALUES (%s, %s::inet, 'expired', 'tester@example.com',
                    NOW() - INTERVAL '1 second')
            """,
            (list_name, ip),
        )
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------

class TestBasicAuth:
    def test_rejects_missing_auth(self, client):
        r = client.get("/api/list?id=default")
        assert r.status_code == 401

    def test_rejects_wrong_credentials(self, client):
        r = client.get("/api/list?id=default", headers=BAD_AUTH)
        assert r.status_code == 401

    def test_accepts_correct_credentials(self, client):
        r = client.get("/api/list?id=default", headers=GOOD_AUTH)
        assert r.status_code == 200

    def test_www_authenticate_header_on_401(self, client):
        r = client.get("/api/list?id=default")
        assert "WWW-Authenticate" in r.headers


class TestListContent:
    def test_empty_list_returns_empty_body(self, client):
        r = client.get("/api/list?id=default", headers=GOOD_AUTH)
        assert r.status_code == 200
        assert r.data == b""

    def test_returns_ips_one_per_line(self, client):
        _insert_entry("default", "1.2.3.4")
        _insert_entry("default", "5.6.7.8")
        r = client.get("/api/list?id=default", headers=GOOD_AUTH)
        lines = r.data.decode().strip().splitlines()
        assert set(lines) == {"1.2.3.4", "5.6.7.8"}

    def test_content_type_plain_text(self, client):
        r = client.get("/api/list?id=default", headers=GOOD_AUTH)
        assert "text/plain" in r.content_type

    def test_does_not_return_other_list_ips(self, client):
        _insert_entry("default", "10.0.0.1")
        _insert_entry("inbound", "10.0.0.2")
        r = client.get("/api/list?id=default", headers=GOOD_AUTH)
        assert "10.0.0.2" not in r.data.decode()
        assert "10.0.0.1" in r.data.decode()

    def test_uses_default_list_when_no_id_param(self, client):
        _insert_entry("default", "9.9.9.9")
        r = client.get("/api/list", headers=GOOD_AUTH)
        assert "9.9.9.9" in r.data.decode()


class TestExpiry:
    def test_expired_entries_not_returned(self, client):
        _insert_expired("default", "1.1.1.1")
        r = client.get("/api/list?id=default", headers=GOOD_AUTH)
        assert "1.1.1.1" not in r.data.decode()

    def test_expired_entries_removed_from_db(self, client):
        _insert_expired("default", "2.2.2.2")
        client.get("/api/list?id=default", headers=GOOD_AUTH)
        conn = psycopg2.connect(**TEST_DB)
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM blocklist_entries WHERE ip = '2.2.2.2'::inet")
            count = cur.fetchone()[0]
        conn.close()
        assert count == 0

    def test_expiry_writes_audit_row(self, client):
        _insert_expired("default", "3.3.3.3")
        client.get("/api/list?id=default", headers=GOOD_AUTH)
        conn = psycopg2.connect(**TEST_DB)
        with conn.cursor() as cur:
            cur.execute(
                "SELECT action, user_email FROM audit_logs WHERE ip = '3.3.3.3'::inet"
            )
            row = cur.fetchone()
        conn.close()
        assert row is not None
        assert row[0] == "expire"
        assert row[1] == "system"

    def test_valid_entries_not_affected_by_expiry_run(self, client):
        _insert_expired("default", "4.4.4.4")
        _insert_entry("default", "5.5.5.5")
        client.get("/api/list?id=default", headers=GOOD_AUTH)
        conn = psycopg2.connect(**TEST_DB)
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM blocklist_entries WHERE ip = '5.5.5.5'::inet")
            count = cur.fetchone()[0]
        conn.close()
        assert count == 1
