"""Tests for GET /api/audit and GET /api/history/<ip>."""

import psycopg2
import pytest

from tests.conftest import TEST_DB


def _audit_row(list_name, ip, action="add", user="tester@example.com", reason="r"):
    conn = psycopg2.connect(**TEST_DB)
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO audit_logs (list_name, ip, action, user_email, reason, expires_at)
            VALUES (%s, %s::inet, %s, %s, %s, NOW() + INTERVAL '7 days')
            """,
            (list_name, ip, action, user, reason),
        )
    conn.commit()
    conn.close()


class TestAuditEndpoint:
    def test_requires_session(self, client):
        r = client.get("/api/audit")
        assert r.status_code == 401

    def test_returns_empty_when_no_logs(self, auth_client):
        r = auth_client.get("/api/audit")
        assert r.status_code == 200
        data = r.get_json()
        assert data["rows"] == []
        assert data["total"] == 0

    def test_returns_rows_in_newest_first_order(self, auth_client):
        for i in range(3):
            _audit_row("default", f"10.0.0.{i+1}")
        r = auth_client.get("/api/audit")
        rows = r.get_json()["rows"]
        assert len(rows) == 3
        timestamps = [row["timestamp"] for row in rows]
        assert timestamps == sorted(timestamps, reverse=True)

    def test_pagination(self, auth_client):
        for i in range(10):
            _audit_row("default", f"10.1.0.{i+1}")
        r = auth_client.get("/api/audit?page=1&per_page=4")
        data = r.get_json()
        assert len(data["rows"]) == 4
        assert data["total"] == 10
        assert data["page"] == 1

    def test_per_page_capped_at_200(self, auth_client):
        r = auth_client.get("/api/audit?per_page=9999")
        # Should not error; per_page silently capped
        assert r.status_code == 200

    def test_filter_by_list(self, auth_client):
        _audit_row("default", "20.0.0.1")
        _audit_row("inbound", "20.0.0.2")
        r = auth_client.get("/api/audit?list=inbound")
        rows = r.get_json()["rows"]
        assert all(row["list_name"] == "inbound" for row in rows)

    def test_row_has_expected_fields(self, auth_client):
        _audit_row("default", "30.0.0.1")
        row = auth_client.get("/api/audit").get_json()["rows"][0]
        for field in ("id", "list_name", "ip", "action", "user_email", "reason", "timestamp"):
            assert field in row


class TestHistoryEndpoint:
    def test_requires_session(self, client):
        r = client.get("/api/history/1.2.3.4")
        assert r.status_code == 401

    def test_returns_empty_for_unknown_ip(self, auth_client):
        r = auth_client.get("/api/history/99.99.99.99")
        assert r.status_code == 200
        assert r.get_json() == []

    def test_returns_all_actions_for_ip(self, auth_client):
        _audit_row("default", "40.0.0.1", action="add")
        _audit_row("default", "40.0.0.1", action="remove")
        r = auth_client.get("/api/history/40.0.0.1")
        data = r.get_json()
        assert len(data) == 2
        actions = {row["action"] for row in data}
        assert actions == {"add", "remove"}

    def test_does_not_return_other_ips(self, auth_client):
        _audit_row("default", "50.0.0.1")
        _audit_row("default", "50.0.0.2")
        r = auth_client.get("/api/history/50.0.0.1")
        data = r.get_json()
        assert all(row["ip"] == "50.0.0.1" for row in data)

    def test_rejects_invalid_ip(self, auth_client):
        r = auth_client.get("/api/history/not-an-ip")
        assert r.status_code == 400
