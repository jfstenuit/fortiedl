"""Housekeeping: expire stale blocklist entries."""

import logging
import syslog as _syslog
from datetime import timezone, datetime

from .db import query, execute

logger = logging.getLogger(__name__)


def _syslog_event(list_name: str, ip: str, action: str, user: str, reason: str) -> None:
    msg = (
        f"blocklist action={action} list={list_name} ip={ip} "
        f"user={user} reason={reason!r}"
    )
    try:
        _syslog.syslog(_syslog.LOG_INFO, msg)
    except Exception:
        pass
    logger.info(msg)


def run_expiry(list_name: str) -> int:
    """Delete expired entries for *list_name*, write audit rows, return count.

    Idempotent: if called with no expired entries → no side effects.
    """
    expired = query(
        """
        SELECT id, list_name, host(ip) AS ip, reason, expires_at
        FROM blocklist_entries
        WHERE list_name = %s AND expires_at < NOW()
        """,
        (list_name,),
    )

    if not expired:
        return 0

    for row in expired:
        execute(
            """
            INSERT INTO audit_logs (list_name, ip, action, user_email, reason, expires_at)
            VALUES (%s, %s::inet, 'expire', 'system', %s, %s)
            """,
            (row["list_name"], row["ip"], row["reason"], row["expires_at"]),
        )
        execute(
            "DELETE FROM blocklist_entries WHERE id = %s",
            (row["id"],),
        )
        _syslog_event(row["list_name"], row["ip"], "expire", "system", row["reason"])

    logger.info("Expired %d entr(ies) from list '%s'.", len(expired), list_name)
    return len(expired)


def write_audit(list_name: str, ip: str, action: str, user_email: str,
                reason: str, expires_at=None) -> None:
    """Insert one audit row and emit a syslog line."""
    execute(
        """
        INSERT INTO audit_logs (list_name, ip, action, user_email, reason, expires_at)
        VALUES (%s, %s::inet, %s, %s, %s, %s)
        """,
        (list_name, ip, action, user_email, reason, expires_at),
    )
    _syslog_event(list_name, ip, action, user_email, reason)
