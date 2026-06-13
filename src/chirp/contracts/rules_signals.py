"""Contract checks for the ``signal()`` primitive.

Dead-binding detection (chirp issue #238 — the dead-ticker class): a template
``{{ signal('x') }}`` / ``sse-swap="x"`` bound to the merged ``/_chirp/live``
connection with **no registered** ``@app.signal('x')`` / ``@app.derived('x')``
producer is a silent dead binding — the element never updates.

Why this needs the explicit producer registry, not AST inference: signal names
are dynamic by nature (``signal(name)``), so the SSE crossref's literal-only
inference degrades to INFO and defeats the #238 goal. This rule validates
``sse-swap`` listeners against ``snapshot.signal_names`` (the registry), which is
authoritative.

All signal bindings resolve to the single ``/_chirp/live`` connection, so this
rule scopes to templates that open an ``sse-connect`` pointing at the signal
stream (directly or via ``signal_connect()``), and validates every ``sse-swap``
in that template against the registry.
"""

from __future__ import annotations

import re

from chirp.contracts.patterns import SSE_CONNECT_TAG as _SSE_CONNECT_TAG_PATTERN
from chirp.contracts.rules_sse import (
    extract_sse_swap_values,
    normalize_sse_url,
    strip_template_comments,
)
from chirp.contracts.types import ContractIssue, Severity

#: Path of the merged signal stream (kept in sync with signal_globals).
SIGNAL_STREAM_PATH = "/_chirp/live"

#: A ``{{ signal('x') }}`` / ``{{ signal_block('x') }}`` binding — the canonical
#: way to bind a signal. The element's ``sse-swap`` is produced at render time, so
#: a literal-``sse-swap`` scan misses it; the helper CALL is the real signal. The
#: ``(?:_block)?`` keeps ``signal_connect(`` / ``make_signal_globals(`` excluded.
_SIGNAL_CALL_PATTERN = re.compile(r"""\bsignal(?:_block)?\s*\(\s*["']([^"']+)["']""")


def _signal_call_names(source: str) -> set[str]:
    """Signal names bound via ``signal('x')`` / ``signal_block('x')`` helper calls."""
    return {m.group(1) for m in _SIGNAL_CALL_PATTERN.finditer(source)}


def _connects_to_signal_stream(source: str) -> bool:
    """Whether *source* opens an ``sse-connect`` pointing at ``/_chirp/live``.

    Matches both a literal ``sse-connect="/_chirp/live..."`` and the
    ``signal_connect()`` global call (which emits that connect at render time and
    appears as a normalized ``__p__`` expression here).
    """
    if "signal_connect()" in source or "signal_connect ()" in source:
        return True
    for match in _SSE_CONNECT_TAG_PATTERN.finditer(source):
        url = normalize_sse_url(match.group("url"))
        if url == SIGNAL_STREAM_PATH or url.startswith(SIGNAL_STREAM_PATH + "?"):
            return True
    return False


def check_signal_bindings(
    template_sources: dict[str, str],
    signal_names: frozenset[str],
) -> list[ContractIssue]:
    """Cross-check signal ``sse-swap`` bindings against registered producers.

    - **Dead binding (ERROR, #238):** an ``sse-swap="x"`` under the signal
      stream with no registered ``signal('x')`` producer.
    - **Orphan producer (INFO):** a registered signal no binding listens for.
    """
    issues: list[ContractIssue] = []
    if not signal_names:
        # No signals registered: a stray /_chirp/live binding would itself be a
        # dead binding, but with no registry there is nothing to validate
        # against here — the SSE crossref / route checks own that case.
        return issues

    bound: set[str] = set()
    for template_name, source in template_sources.items():
        if template_name.startswith("chirp/"):
            continue
        source = strip_template_comments(source)
        # ``signal('x')`` / ``signal_block('x')`` helper calls are unambiguous
        # signal bindings wherever they appear — the shell's ``signal_connect()``
        # wraps every page, so the binding need not sit in the same template that
        # opens the connection. A literal ``sse-swap="x"`` only counts as a signal
        # binding when this template actually connects to ``/_chirp/live`` (a raw
        # sse-swap may listen on a different SSE stream).
        names = _signal_call_names(source)
        if _connects_to_signal_stream(source):
            names |= extract_sse_swap_values(source)
        if not names:
            continue
        bound.update(names)
        dead = sorted(names - signal_names)
        issues.extend(
            ContractIssue(
                severity=Severity.ERROR,
                category="signal_dead_binding",
                message=(
                    f'signal binding sse-swap="{name}" has no registered producer. '
                    f"Declare it with @app.signal({name!r}) or @app.derived({name!r}, ...), "
                    "or fix the name. A bound signal with no producer never updates (#238)."
                ),
                template=template_name,
                details=f"Registered signals: {', '.join(sorted(signal_names)) or '(none)'}",
            )
            for name in dead
        )

    orphans = sorted(signal_names - bound)
    issues.extend(
        ContractIssue(
            severity=Severity.INFO,
            category="signal_orphan",
            message=(
                f"signal {name!r} is registered but no template binds it with "
                "signal()/signal_block(). It will be produced but never displayed."
            ),
        )
        for name in orphans
    )
    return issues
