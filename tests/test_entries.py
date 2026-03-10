"""Tests for the entries CRUD API (session-authenticated)."""

import json
import psycopg2
import pytest

from tests.conftest import TEST_DB, CSRF


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _insert(list_name, ip, reason="block reason", days=7):
    conn = psycopg2.connect(**TEST_DB)
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO blocklist_entries (list_name, ip, reason, added_by, expires_at)
            VALUES (%s, %s::inet, %s, 'tester@example.com',
                    NOW() + (%s || ' days')::interval)
            RETURNING id
            """,
            (list_name, ip, reason, str(days)),
        )
        row_id = cur.fetchone()[0]
    conn.commit()
    conn.close()
    return row_id


def _count(list_name=None, ip=None):
    conn = psycopg2.connect(**TEST_DB)
    with conn.cursor() as cur:
        if ip:
            cur.execute("SELECT COUNT(*) FROM blocklist_entries WHERE ip = %s::inet", (ip,))
        else:
            cur.execute("SELECT COUNT(*) FROM blocklist_entries WHERE list_name = %s", (list_name,))
        n = cur.fetchone()[0]
    conn.close()
    return n


# ---------------------------------------------------------------------------

class TestGetEntries:
    def test_requires_session(self, client):
        r = client.get("/api/entries?list=default")
        assert r.status_code == 401

    def test_returns_empty_list(self, auth_client):
        r = auth_client.get("/api/entries?list=default")
        assert r.status_code == 200
        assert r.get_json() == []

    def test_returns_entries_for_list(self, auth_client):
        _insert("default", "10.0.0.1")
        _insert("default", "10.0.0.2")
        _insert("inbound", "10.0.0.3")
        r = auth_client.get("/api/entries?list=default")
        data = r.get_json()
        assert len(data) == 2
        ips = {e["ip"] for e in data}
        assert ips == {"10.0.0.1", "10.0.0.2"}

    def test_entry_has_expected_fields(self, auth_client):
        _insert("default", "11.0.0.1")
        r = auth_client.get("/api/entries?list=default")
        e = r.get_json()[0]
        for field in ("id", "list_name", "ip", "reason", "added_by", "added_at", "expires_at"):
            assert field in e


class TestCreateEntry:
    def test_requires_session(self, client):
        r = client.post("/api/entries",
                        json={"ip": "1.2.3.4", "reason": "test", "list_name": "default", "expires_in": "1w"},
                        headers={"X-CSRF-Token": CSRF, "Content-Type": "application/json"})
        assert r.status_code == 401

    def test_requires_csrf(self, auth_client):
        r = auth_client.post("/api/entries",
                             json={"ip": "1.2.3.4", "reason": "test", "list_name": "default", "expires_in": "1w"},
                             headers={"Content-Type": "application/json"})
        assert r.status_code == 403

    def test_creates_entry(self, auth_client, csrf_headers):
        r = auth_client.post("/api/entries",
                             json={"ip": "1.2.3.4", "reason": "test block", "list_name": "default", "expires_in": "1w"},
                             headers=csrf_headers)
        assert r.status_code == 201
        assert r.get_json()["ip"] == "1.2.3.4"
        assert _count(ip="1.2.3.4") == 1

    def test_rejects_invalid_ip(self, auth_client, csrf_headers):
        r = auth_client.post("/api/entries",
                             json={"ip": "not-an-ip", "reason": "test", "list_name": "default", "expires_in": "1w"},
                             headers=csrf_headers)
        assert r.status_code == 400

    def test_rejects_missing_reason(self, auth_client, csrf_headers):
        r = auth_client.post("/api/entries",
                             json={"ip": "1.2.3.4", "reason": "", "list_name": "default", "expires_in": "1w"},
                             headers=csrf_headers)
        assert r.status_code == 400

    def test_rejects_invalid_expires_in(self, auth_client, csrf_headers):
        r = auth_client.post("/api/entries",
                             json={"ip": "1.2.3.4", "reason": "test", "list_name": "default", "expires_in": "99y"},
                             headers=csrf_headers)
        assert r.status_code == 400

    def test_rejects_duplicate_ip_in_same_list(self, auth_client, csrf_headers):
        _insert("default", "2.2.2.2")
        r = auth_client.post("/api/entries",
                             json={"ip": "2.2.2.2", "reason": "dup", "list_name": "default", "expires_in": "1w"},
                             headers=csrf_headers)
        assert r.status_code == 409

    def test_allows_same_ip_in_different_lists(self, auth_client, csrf_headers):
        _insert("default", "3.3.3.3")
        r = auth_client.post("/api/entries",
                             json={"ip": "3.3.3.3", "reason": "other list", "list_name": "inbound", "expires_in": "1w"},
                             headers=csrf_headers)
        assert r.status_code == 201

    def test_writes_audit_log(self, auth_client, csrf_headers):
        auth_client.post("/api/entries",
                         json={"ip": "4.4.4.4", "reason": "audit check", "list_name": "default", "expires_in": "1w"},
                         headers=csrf_headers)
        conn = psycopg2.connect(**TEST_DB)
        with conn.cursor() as cur:
            cur.execute(
                "SELECT action, user_email FROM audit_logs WHERE ip = '4.4.4.4'::inet"
            )
            row = cur.fetchone()
        conn.close()
        assert row is not None
        assert row[0] == "add"
        assert row[1] == "tester@example.com"

    def test_accepts_ipv6(self, auth_client, csrf_headers):
        r = auth_client.post("/api/entries",
                             json={"ip": "2001:db8::1", "reason": "ipv6 test", "list_name": "default", "expires_in": "1d"},
                             headers=csrf_headers)
        assert r.status_code == 201

    def test_rejects_invalid_list_name(self, auth_client, csrf_headers):
        r = auth_client.post("/api/entries",
                             json={"ip": "5.5.5.5", "reason": "x", "list_name": "bad name;drop", "expires_in": "1w"},
                             headers=csrf_headers)
        assert r.status_code == 400


class TestDeleteEntry:
    def test_requires_session(self, client):
        r = client.delete("/api/entries/1.2.3.4?list=default",
                          headers={"X-CSRF-Token": CSRF})
        assert r.status_code == 401

    def test_requires_csrf(self, auth_client):
        _insert("default", "6.6.6.6")
        r = auth_client.delete("/api/entries/6.6.6.6?list=default")
        assert r.status_code == 403

    def test_deletes_entry(self, auth_client, csrf_headers):
        _insert("default", "7.7.7.7")
        r = auth_client.delete("/api/entries/7.7.7.7?list=default", headers=csrf_headers)
        assert r.status_code == 204
        assert _count(ip="7.7.7.7") == 0

    def test_returns_404_for_missing_entry(self, auth_client, csrf_headers):
        r = auth_client.delete("/api/entries/99.99.99.99?list=default", headers=csrf_headers)
        assert r.status_code == 404

    def test_delete_writes_audit_remove(self, auth_client, csrf_headers):
        _insert("default", "8.8.8.8")
        auth_client.delete("/api/entries/8.8.8.8?list=default", headers=csrf_headers)
        conn = psycopg2.connect(**TEST_DB)
        with conn.cursor() as cur:
            cur.execute(
                "SELECT action FROM audit_logs WHERE ip = '8.8.8.8'::inet"
            )
            row = cur.fetchone()
        conn.close()
        assert row is not None
        assert row[0] == "remove"

    def test_only_deletes_from_specified_list(self, auth_client, csrf_headers):
        _insert("default", "9.9.9.9")
        _insert("inbound", "9.9.9.9")
        auth_client.delete("/api/entries/9.9.9.9?list=default", headers=csrf_headers)
        assert _count(ip="9.9.9.9") == 1  # inbound still present


class TestUpdateEntry:
    def test_requires_csrf(self, auth_client):
        _insert("default", "10.10.10.10")
        r = auth_client.put("/api/entries/10.10.10.10",
                            json={"list_name": "default", "expires_in": "1m"},
                            headers={"Content-Type": "application/json"})
        assert r.status_code == 403

    def test_updates_reason(self, auth_client, csrf_headers):
        _insert("default", "11.11.11.11")
        r = auth_client.put("/api/entries/11.11.11.11",
                            json={"list_name": "default", "reason": "updated reason"},
                            headers=csrf_headers)
        assert r.status_code == 200
        assert r.get_json()["reason"] == "updated reason"

    def test_returns_404_for_missing_entry(self, auth_client, csrf_headers):
        r = auth_client.put("/api/entries/100.100.100.100",
                            json={"list_name": "default", "reason": "nope"},
                            headers=csrf_headers)
        assert r.status_code == 404
