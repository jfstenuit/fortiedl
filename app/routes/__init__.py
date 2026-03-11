"""Shared helpers for route modules."""

import os


def get_available_lists() -> list[str]:
    """Return the ordered list of configured list names from AVAILABLE_LISTS."""
    raw = os.environ.get("AVAILABLE_LISTS", "default")
    return [name.strip() for name in raw.split(",") if name.strip()]


def get_default_list() -> str:
    """Return the first (default) list name."""
    return get_available_lists()[0]
