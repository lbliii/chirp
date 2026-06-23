"""Wire-format encoding for query parameters (extended-query text format)."""

from __future__ import annotations

from datetime import date, datetime, time
from decimal import Decimal
from typing import Any
from uuid import UUID


def encode_param(value: Any) -> bytes | None:
    """Encode a Python value as a PostgreSQL text-format parameter."""
    if value is None:
        return None
    if isinstance(value, bool):
        return b"t" if value else b"f"
    if isinstance(value, int):
        return str(value).encode("ascii")
    if isinstance(value, float):
        return repr(value).encode("ascii")
    if isinstance(value, Decimal):
        return format(value, "f").encode("ascii")
    if isinstance(value, bytes):
        return "\\x" + value.hex().encode("ascii")
    if isinstance(value, str):
        return value.encode("utf-8")
    if isinstance(value, UUID):
        return str(value).encode("ascii")
    if isinstance(value, datetime):
        return value.isoformat(sep=" ").encode("ascii")
    if isinstance(value, date):
        return value.isoformat().encode("ascii")
    if isinstance(value, time):
        return value.isoformat().encode("ascii")
    return str(value).encode("utf-8")
