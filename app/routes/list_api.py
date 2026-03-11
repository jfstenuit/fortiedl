"""GET /api/list  — EDL endpoint consumed by the firewall (Basic Auth)."""

import os
import secrets

from flask import Blueprint, request, abort, Response

from ..db import query
from ..expiry import run_expiry
from . import get_default_list

list_api_bp = Blueprint("list_api", __name__)


def _check_basic_auth() -> bool:
    auth = request.authorization
    if not auth:
        return False
    expected_user = os.environ.get("LIST_BASIC_AUTH_USER", "")
    expected_pass = os.environ.get("LIST_BASIC_AUTH_PASSWORD", "")
    user_ok = secrets.compare_digest(auth.username or "", expected_user)
    pass_ok = secrets.compare_digest(auth.password or "", expected_pass)
    return user_ok and pass_ok


@list_api_bp.route("/api/list")
def get_list():
    if not _check_basic_auth():
        return Response(
            "Unauthorized",
            401,
            {"WWW-Authenticate": 'Basic realm="EDL"'},
        )

    list_name = request.args.get("id", get_default_list())

    # Housekeeping: expire stale entries before building the list
    run_expiry(list_name)

    rows = query(
        "SELECT DISTINCT host(ip) AS ip FROM blocklist_entries WHERE list_name = %s ORDER BY 1",
        (list_name,),
    )

    body = "\n".join(r["ip"] for r in rows)
    if body:
        body += "\n"

    return Response(body, mimetype="text/plain")
