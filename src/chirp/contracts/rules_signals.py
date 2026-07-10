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
from typing import Any

from chirp.contracts.patterns import SSE_CONNECT_TAG as _SSE_CONNECT_TAG_PATTERN
from chirp.contracts.rules_sse import (
    extract_sse_swap_values,
    normalize_sse_url,
    strip_template_comments,
)
from chirp.contracts.types import ContractIssue, Severity

_SESSION_MIDDLEWARE = "SessionMiddleware"
_SESSION_SIGNAL_MIDDLEWARE = "SessionSignalMiddleware"

#: Path of the merged signal stream (kept in sync with signal_globals).
SIGNAL_STREAM_PATH = "/_chirp/live"

#: A ``{{ signal('x') }}`` / ``{{ signal_block('x') }}`` / ``{{ signal_bind('x') }}``
#: binding — the canonical ways to bind a signal. The element's ``sse-swap`` is
#: produced at render time, so a literal-``sse-swap`` scan misses it; the helper
#: CALL is the real signal. ``(?:_block|_bind|_attrs)?`` keeps ``signal_connect(`` /
#: ``make_signal_globals(`` excluded.
_SIGNAL_CALL_PATTERN = re.compile(r"""\bsignal(?:_block|_bind|_attrs)?\s*\(\s*["']([^"']+)["']""")
#: ``sse_scope(url)`` opens a dedicated non-signal SSE stream (see chirp/sse.html).
_SSE_SCOPE_PATTERN = re.compile(r"\bsse_scope\s*\(")
_HTMX4_SIGNAL_CONNECT_PATTERN = re.compile(
    r"\bhx-sse:connect\s*=\s*[\"'](?P<url>[^\"']+)[\"']",
    re.IGNORECASE,
)
_SIGNAL_MARKER_PATTERN = re.compile(
    r"\bdata-chirp-signal\s*=\s*[\"']([^\"']+)[\"']",
    re.IGNORECASE,
)


def _signal_call_names(source: str) -> set[str]:
    """Signal names bound via ``signal()`` / ``signal_block()`` / ``signal_bind()`` calls."""
    return {m.group(1) for m in _SIGNAL_CALL_PATTERN.finditer(source)}


def _count_signal_stream_connects(source: str) -> int:
    """Count ``/_chirp/live`` connect sites in *source*."""
    count = source.count("signal_connect()") + source.count("signal_connect ()")
    for match in _SSE_CONNECT_TAG_PATTERN.finditer(source):
        url = normalize_sse_url(match.group("url"))
        if url == SIGNAL_STREAM_PATH or url.startswith(SIGNAL_STREAM_PATH + "?"):
            count += 1
    for match in _HTMX4_SIGNAL_CONNECT_PATTERN.finditer(source):
        url = normalize_sse_url(match.group("url"))
        if url == SIGNAL_STREAM_PATH or url.startswith(SIGNAL_STREAM_PATH + "?"):
            count += 1
    return count


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
    for match in _HTMX4_SIGNAL_CONNECT_PATTERN.finditer(source):
        url = normalize_sse_url(match.group("url"))
        if url == SIGNAL_STREAM_PATH or url.startswith(SIGNAL_STREAM_PATH + "?"):
            return True
    return False


def _has_competing_sse_connect(source: str) -> bool:
    """Whether *source* opens an ``sse-connect`` to a non-signal stream."""
    if _SSE_SCOPE_PATTERN.search(source):
        return True
    for match in _SSE_CONNECT_TAG_PATTERN.finditer(source):
        url = normalize_sse_url(match.group("url"))
        if url != SIGNAL_STREAM_PATH and not url.startswith(SIGNAL_STREAM_PATH + "?"):
            return True
    for match in _HTMX4_SIGNAL_CONNECT_PATTERN.finditer(source):
        url = normalize_sse_url(match.group("url"))
        if url != SIGNAL_STREAM_PATH and not url.startswith(SIGNAL_STREAM_PATH + "?"):
            return True
    return False


def _raw_sse_swap_names(source: str) -> set[str]:
    """Hand-written ``sse-swap`` values, excluding ``signal*()`` helper bindings."""
    return extract_sse_swap_values(source) - _signal_call_names(source)


def _raw_signal_marker_names(source: str) -> set[str]:
    """Hand-written htmx 4 signal markers outside the template helpers."""
    return {match.group(1) for match in _SIGNAL_MARKER_PATTERN.finditer(source)}


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

    signal_stream_active = any(
        _connects_to_signal_stream(src)
        for name, src in template_sources.items()
        if not name.startswith("chirp/")
    )

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
        connects_here = _connects_to_signal_stream(source)
        raw_sse = _raw_sse_swap_names(source)
        raw_markers = _raw_signal_marker_names(source)
        if connects_here:
            names |= extract_sse_swap_values(source)
            names |= raw_markers
        elif (
            signal_stream_active
            and not _has_competing_sse_connect(source)
            and (raw_sse or raw_markers)
        ):
            # Composed page under a layout's signal_connect() (#316): the layout
            # owns the /_chirp/live connect, so validate hand-written sse-swap here.
            names |= raw_sse
            names |= raw_markers
            issues.extend(
                ContractIssue(
                    severity=Severity.INFO,
                    category="signal_raw_sse_swap",
                    message=(
                        f'Raw sse-swap="{name}" in a template composed under '
                        "signal_connect() — prefer "
                        f"{{{{ signal_bind({name!r}) }}}} so the binding is validated."
                    ),
                    template=template_name,
                )
                for name in sorted(raw_sse)
            )
            issues.extend(
                ContractIssue(
                    severity=Severity.INFO,
                    category="signal_raw_marker",
                    message=(
                        f'Raw data-chirp-signal="{name}" in a template composed under '
                        "signal_connect() — prefer "
                        f"{{{{ signal_bind({name!r}) }}}} so topic scoping stays exact."
                    ),
                    template=template_name,
                )
                for name in sorted(raw_markers)
            )
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
                "signal()/signal_block()/signal_bind(). It will be produced but "
                "never displayed."
            ),
        )
        for name in orphans
    )
    return issues


def check_signal_scope(
    middleware_list: list[Any],
    session_signal_names: frozenset[str],
) -> list[ContractIssue]:
    """Error when session-scoped signals exist without ``SessionMiddleware``.

    Session-scoped signals resolve their audience key from the session; without
    ``SessionMiddleware`` the key is never available and per-visitor fan-out is
    silently broken.
    """
    if not session_signal_names:
        return []
    middleware_names = {type(mw).__name__ for mw in middleware_list}
    missing = [
        name
        for name in (_SESSION_MIDDLEWARE, _SESSION_SIGNAL_MIDDLEWARE)
        if name not in middleware_names
    ]
    if not missing:
        return []
    names = ", ".join(sorted(session_signal_names))
    required = " and ".join(missing)
    return [
        ContractIssue(
            severity=Severity.ERROR,
            category="signal_scope",
            message=(
                f"Session-scoped signal(s) ({names}) require {required} "
                "so each connection can authorize its trusted server-side audience "
                "for /_chirp/live. Register both SessionMiddleware and "
                "SessionSignalMiddleware before using "
                "audience='session' signals."
            ),
        )
    ]


def check_signal_mixed_audience_derived(
    mixed_audience_derived_names: frozenset[str],
) -> list[ContractIssue]:
    """Warn when a derived signal depends on both global and session signals."""
    return [
        ContractIssue(
            severity=Severity.WARNING,
            category="signal_scope",
            message=(
                f"Derived signal {name!r} depends on both global and session-scoped "
                "signals. The derived inherits session scope, but mixing audiences "
                "often means the compute() reads a global dep that will not vary "
                "per visitor — verify the dependency graph is intentional."
            ),
        )
        for name in sorted(mixed_audience_derived_names)
    ]


def check_signal_connect_budget(
    template_sources: dict[str, str],
) -> list[ContractIssue]:
    """INFO when more than one persistent ``/_chirp/live`` scope is opened.

    Browsers cap concurrent SSE connections per origin (HTTP/1.1 footgun). One
    ``signal_connect()`` wrapper per composed page is the supported pattern.
    """
    issues: list[ContractIssue] = []
    templates_with_connect: list[str] = []
    for template_name, source in template_sources.items():
        if template_name.startswith("chirp/"):
            continue
        stripped = strip_template_comments(source)
        count = _count_signal_stream_connects(stripped)
        if count > 1:
            issues.append(
                ContractIssue(
                    severity=Severity.INFO,
                    category="signal_connect_budget",
                    message=(
                        f"Template {template_name!r} opens {count} persistent "
                        "/_chirp/live scopes — merge into one signal_connect() "
                        "wrapper so the browser uses a single SSE connection."
                    ),
                    template=template_name,
                )
            )
        if count > 0:
            templates_with_connect.append(template_name)
    if len(templates_with_connect) > 1:
        joined = ", ".join(sorted(templates_with_connect))
        issues.append(
            ContractIssue(
                severity=Severity.INFO,
                category="signal_connect_budget",
                message=(
                    f"{len(templates_with_connect)} templates each open /_chirp/live "
                    f"({joined}). When composed on one page this nests multiple "
                    "persistent SSE scopes — prefer a single signal_connect() in "
                    "the shell layout."
                ),
            )
        )
    return issues
