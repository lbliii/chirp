"""Structured logging with request correlation.

Provides request_id propagation via ContextVar and a structured_log helper
for JSON-formatted logs with request_id, user_id, path, etc.
"""

import json
import logging
from contextvars import ContextVar
from typing import Any

request_id_var: ContextVar[str | None] = ContextVar("chirp_request_id", default=None)


def get_request_id() -> str | None:
    """Return the current request ID, or None if outside a request context."""
    return request_id_var.get()


def structured_log(
    level: int,
    message: str,
    *,
    request_id: str | None = None,
    user_id: str | None = None,
    path: str | None = None,
    method: str | None = None,
    **extra: Any,
) -> None:
    """Log a structured JSON message with correlation fields.

    Merges request_id from context if not provided. Use for audit trails
    and observability pipelines that expect JSON logs.
    """
    rid = request_id or get_request_id()
    payload: dict[str, Any] = {"message": message, **extra}
    if rid is not None:
        payload["request_id"] = rid
    if user_id is not None:
        payload["user_id"] = user_id
    if path is not None:
        payload["path"] = path
    if method is not None:
        payload["method"] = method
    logger = logging.getLogger("chirp")
    logger.log(level, json.dumps(payload))
