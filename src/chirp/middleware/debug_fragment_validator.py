"""Debug-mode validator for fragment responses.

Catches silent failure modes where a fragment response would paint a
broken page in the browser:

- ``<!DOCTYPE`` in fragment body (a full page rendered into an outlet).
- Duplicate ``id="..."`` for registered shell-region ids (would collide
  with the live DOM after the swap).

Only active when ``AppConfig.debug=True``; auto-registered during
``_collect_builtin_middleware`` when an OOB registry is present. Warns
by default; ``strict=True`` raises instead for CI enforcement.
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

from chirp.errors import ChirpError
from chirp.http.request import Request
from chirp.http.response import Response
from chirp.middleware.protocol import AnyResponse, Next

if TYPE_CHECKING:
    from chirp.templating.oob_registry import OOBRegistry

_LOG = logging.getLogger("chirp.middleware.debug_fragment_validator")

_DOCTYPE_RE = re.compile(r"<!doctype", re.IGNORECASE)


class FragmentValidationError(ChirpError):
    """Raised by ``DebugFragmentValidator`` in strict mode when a
    fragment response leaks full-page markup or duplicate ids."""


class DebugFragmentValidator:
    """Middleware that inspects fragment responses for breakage patterns.

    Only inspects buffered ``Response`` objects with ``text/html`` content
    when ``render_intent == "fragment"`` (or ``"unknown"`` on an htmx
    request, matching :class:`HTMLInject`'s skip rule).

    Streaming responses are skipped — buffering them would defeat the
    point of streaming and the body is rarely available as a single
    string anyway.
    """

    __slots__ = ("_oob_registry", "_strict")

    def __init__(self, oob_registry: OOBRegistry, *, strict: bool = False) -> None:
        self._oob_registry = oob_registry
        self._strict = strict

    async def __call__(self, request: Request, next: Next) -> AnyResponse:
        response = await next(request)
        if not isinstance(response, Response):
            return response
        if "text/html" not in response.content_type:
            return response
        if not self._should_inspect(response, request):
            return response

        body = response.body
        if isinstance(body, bytes):
            body = body.decode("utf-8", errors="replace")
        if not body:
            return response

        issues = self._scan(body)
        if not issues:
            return response

        target = request.htmx_target_id
        for issue in issues:
            _LOG.warning(
                "fragment validator: %s (path=%s, target=%s)",
                issue,
                request.path,
                target,
            )
        if self._strict:
            raise FragmentValidationError("; ".join(issues))
        return response

    @staticmethod
    def _should_inspect(response: Response, request: Request) -> bool:
        intent = response.render_intent
        if intent == "fragment":
            return True
        if intent == "unknown" and request.is_htmx:
            return True
        return False

    def _scan(self, body: str) -> list[str]:
        issues: list[str] = []
        if _DOCTYPE_RE.search(body):
            issues.append("<!DOCTYPE> in fragment body (full page rendered into outlet)")

        target_ids = self._shell_region_target_ids()
        for tid in target_ids:
            count = _count_id_occurrences(body, tid)
            if count > 1:
                issues.append(f'duplicate id="{tid}" ({count} occurrences)')
        return issues

    def _shell_region_target_ids(self) -> frozenset[str]:
        reg = self._oob_registry
        ids: set[str] = set()
        for block_name in reg.registered_blocks:
            cfg = reg.get(block_name)
            if cfg is not None:
                ids.add(cfg.target_id)
        return frozenset(ids)


def _count_id_occurrences(body: str, target_id: str) -> int:
    """Count ``id="target_id"`` and ``id='target_id'`` occurrences."""
    if not target_id:
        return 0
    double = body.count(f'id="{target_id}"')
    single = body.count(f"id='{target_id}'")
    return double + single
