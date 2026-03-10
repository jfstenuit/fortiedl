"""Read-only audit endpoints."""

from flask import Blueprint, request, jsonify, abort

from ..auth import require_session
from ..db import query

audit_bp = Blueprint("audit", __name__)


@audit_bp.route("/api/audit")
@require_session
def get_audit():
    """Paginated audit log; optionally filtered by list."""
    try:
        page = max(1, int(request.args.get("page", 1)))
        per_page = min(200, max(1, int(request.args.get("per_page", 50))))
    except ValueError:
        abort(400, "page and per_page must be integers")

    list_name = request.args.get("list")
    offset = (page - 1) * per_page

    if list_name:
        rows = query(
            """
            SELECT id, list_name, host(ip) AS ip, action, user_email,
                   reason, expires_at, timestamp
            FROM audit_logs
            WHERE list_name = %s
            ORDER BY timestamp DESC
            LIMIT %s OFFSET %s
            """,
            (list_name, per_page, offset),
        )
        total_row = query(
            "SELECT COUNT(*) AS n FROM audit_logs WHERE list_name = %s",
            (list_name,),
            fetch="one",
        )
    else:
        rows = query(
            """
            SELECT id, list_name, host(ip) AS ip, action, user_email,
                   reason, expires_at, timestamp
            FROM audit_logs
            ORDER BY timestamp DESC
            LIMIT %s OFFSET %s
            """,
            (per_page, offset),
        )
        total_row = query("SELECT COUNT(*) AS n FROM audit_logs", fetch="one")

    return jsonify({
        "page": page,
        "per_page": per_page,
        "total": total_row["n"],
        "rows": rows,
    })


@audit_bp.route("/api/history/<path:ip>")
@require_session
def get_history(ip: str):
    import ipaddress
    try:
        ipaddress.ip_address(ip)
    except ValueError:
        abort(400, "Invalid IP address")

    rows = query(
        """
        SELECT id, list_name, host(ip) AS ip, action, user_email,
               reason, expires_at, timestamp
        FROM audit_logs
        WHERE ip = %s::inet
        ORDER BY timestamp DESC
        """,
        (ip,),
    )
    return jsonify(rows)
