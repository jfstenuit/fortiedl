"""CRUD for blocklist entries (session-authenticated)."""

import os
import ipaddress
import logging
from datetime import datetime, timedelta, timezone

from flask import Blueprint, request, jsonify, session, abort

from ..auth import require_session, require_csrf
from ..db import query, execute
from ..expiry import write_audit
from . import get_available_lists, get_default_list

logger = logging.getLogger(__name__)

entries_bp = Blueprint("entries", __name__)

EXPIRY_MAP: dict[str, timedelta] = {
    "1d": timedelta(days=1),
    "1w": timedelta(weeks=1),
    "1m": timedelta(days=30),
    "3m": timedelta(days=90),
    "6m": timedelta(days=180),
    "1y": timedelta(days=365),
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _valid_ip(value: str) -> bool:
    try:
        ipaddress.ip_address(value)
        return True
    except ValueError:
        return False


def _valid_list(name: str) -> bool:
    """Only allow safe list names (alphanumeric, dash, underscore)."""
    import re
    return bool(re.fullmatch(r"[a-zA-Z0-9_-]{1,64}", name))


def _expires_at(expires_in: str) -> datetime:
    delta = EXPIRY_MAP.get(expires_in)
    if delta is None:
        abort(400, f"Invalid expires_in value '{expires_in}'. Allowed: {list(EXPIRY_MAP)}")
    return datetime.now(tz=timezone.utc) + delta


def _current_user() -> str:
    return session["user"]["email"]


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@entries_bp.route("/api/lists")
@require_session
def list_names():
    """Return configured lists (AVAILABLE_LISTS) plus any extra names in the DB."""
    configured = get_available_lists()
    rows = query("SELECT DISTINCT list_name FROM blocklist_entries ORDER BY list_name")
    db_names = [r["list_name"] for r in rows]
    # Configured lists first (preserving order), then any DB-only extras
    extras = [n for n in db_names if n not in configured]
    return jsonify(configured + extras)


@entries_bp.route("/api/entries")
@require_session
def get_entries():
    list_name = request.args.get("list", get_default_list())
    rows = query(
        """
        SELECT id, list_name, host(ip) AS ip, reason, added_by, added_at, expires_at
        FROM blocklist_entries
        WHERE list_name = %s
        ORDER BY added_at DESC
        """,
        (list_name,),
    )
    return jsonify(rows)


@entries_bp.route("/api/entries", methods=["POST"])
@require_session
@require_csrf
def create_entry():
    body = request.get_json(silent=True) or {}
    ip = (body.get("ip") or "").strip()
    reason = (body.get("reason") or "").strip()
    list_name = (body.get("list_name") or get_default_list()).strip()
    expires_in = body.get("expires_in", "1w")

    if not ip:
        abort(400, "ip is required")
    if not _valid_ip(ip):
        abort(400, f"'{ip}' is not a valid IP address")
    if not reason:
        abort(400, "reason is required")
    if not _valid_list(list_name):
        abort(400, "Invalid list name")

    expires = _expires_at(expires_in)
    actor = _current_user()

    try:
        execute(
            """
            INSERT INTO blocklist_entries (list_name, ip, reason, added_by, expires_at)
            VALUES (%s, %s::inet, %s, %s, %s)
            """,
            (list_name, ip, reason, actor, expires),
        )
    except Exception as exc:
        if "uq_list_ip" in str(exc):
            abort(409, f"IP {ip} already exists in list '{list_name}'")
        logger.exception("DB error on insert")
        abort(500, "Database error")

    write_audit(list_name, ip, "add", actor, reason, expires)

    row = query(
        """
        SELECT id, list_name, host(ip) AS ip, reason, added_by, added_at, expires_at
        FROM blocklist_entries WHERE list_name = %s AND ip = %s::inet
        """,
        (list_name, ip),
        fetch="one",
    )
    return jsonify(row), 201


@entries_bp.route("/api/entries/<path:ip>", methods=["PUT"])
@require_session
@require_csrf
def update_entry(ip: str):
    body = request.get_json(silent=True) or {}
    list_name = (body.get("list_name") or get_default_list()).strip()
    reason = (body.get("reason") or "").strip()
    expires_in = body.get("expires_in")

    if not _valid_ip(ip):
        abort(400, "Invalid IP address")
    if not _valid_list(list_name):
        abort(400, "Invalid list name")

    existing = query(
        "SELECT id FROM blocklist_entries WHERE list_name = %s AND ip = %s::inet",
        (list_name, ip),
        fetch="one",
    )
    if not existing:
        abort(404, "Entry not found")

    updates = {}
    if reason:
        updates["reason"] = reason
    if expires_in:
        updates["expires_at"] = _expires_at(expires_in)

    if not updates:
        abort(400, "Nothing to update")

    set_parts = [f"{col} = %s" for col in updates]
    values = list(updates.values()) + [list_name, ip]

    execute(
        f"UPDATE blocklist_entries SET {', '.join(set_parts)} "
        "WHERE list_name = %s AND ip = %s::inet",
        values,
    )

    actor = _current_user()
    write_audit(
        list_name, ip, "add", actor,
        reason or f"updated expiry to {expires_in}",
        updates.get("expires_at"),
    )

    row = query(
        """
        SELECT id, list_name, host(ip) AS ip, reason, added_by, added_at, expires_at
        FROM blocklist_entries WHERE list_name = %s AND ip = %s::inet
        """,
        (list_name, ip),
        fetch="one",
    )
    return jsonify(row)


@entries_bp.route("/api/entries/<path:ip>", methods=["DELETE"])
@require_session
@require_csrf
def delete_entry(ip: str):
    list_name = request.args.get("list", get_default_list())

    if not _valid_ip(ip):
        abort(400, "Invalid IP address")
    if not _valid_list(list_name):
        abort(400, "Invalid list name")

    existing = query(
        "SELECT reason FROM blocklist_entries WHERE list_name = %s AND ip = %s::inet",
        (list_name, ip),
        fetch="one",
    )
    if not existing:
        abort(404, "Entry not found")

    actor = _current_user()
    execute(
        "DELETE FROM blocklist_entries WHERE list_name = %s AND ip = %s::inet",
        (list_name, ip),
    )
    write_audit(list_name, ip, "remove", actor, existing["reason"])

    return "", 204
