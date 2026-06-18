"""SSE contract cross-checks."""

import ast
import inspect
import re
import textwrap
from typing import Any

from chirp.routing.router import Router

from .declarations import SSEContract
from .patterns import KIDA_EXPR as _KIDA_EXPR_PATTERN
from .patterns import SSE_CONNECT_TAG as _SSE_CONNECT_TAG_PATTERN
from .routes import build_route_index, find_matching_route
from .types import ContractIssue, Severity

# Auth accessors that resolve the request user inside an SSE generator. These
# return the connect-time-pinned user once the runtime capture is in place
# (Anonymous when no AuthMiddleware is wired). Detected by call name.
_USER_ACCESSORS = frozenset({"get_user", "current_user"})

# Middleware that establishes the auth user ContextVar — detected by class NAME
# (never isinstance, never importing middleware into the contracts layer),
# mirroring rules_auth_meta / rules_security_stack.
_AUTH_MIDDLEWARE = "AuthMiddleware"

_SSE_SWAP_VALUE_PATTERN = re.compile(r'\bsse-swap\s*=\s*["\']([^"\']+)["\']', re.IGNORECASE)

#: Kida ({# … #}, including {#- -#}) and HTML (<!-- … -->) comments. An
#: sse-connect / sse-swap that appears only inside a comment is illustrative
#: documentation, not a real element — scanning it yields false positives (e.g.
#: an unmitigated sse-connect shown in a how-it-works comment flagged as an
#: ERROR). Strip comments before any element scan.
_TEMPLATE_COMMENT_PATTERN = re.compile(r"\{#.*?#\}|<!--.*?-->", re.DOTALL)


def strip_template_comments(source: str) -> str:
    """Remove Kida + HTML comments so element scans ignore illustrative markup."""
    return _TEMPLATE_COMMENT_PATTERN.sub("", source)


def normalize_sse_url(url: str) -> str:
    """Replace Kida expressions so route-pattern matching still works."""
    return _KIDA_EXPR_PATTERN.sub("__p__", url).strip()


def extract_sse_swap_values(source: str) -> set[str]:
    """Extract all sse-swap event names from source (comments stripped)."""
    stripped = strip_template_comments(source)
    return {match.group(1) for match in _SSE_SWAP_VALUE_PATTERN.finditer(stripped)}


def _call_name(node: ast.expr) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _string_kwarg(node: ast.Call, name: str) -> tuple[bool, str | None]:
    """Return ``(confident, value)`` for a string keyword argument."""
    for kw in node.keywords:
        if kw.arg != name:
            continue
        if isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
            return True, kw.value.value
        if isinstance(kw.value, ast.Constant) and kw.value.value is None:
            return True, None
        return False, None
    return True, None


class _UserReadFinder(ast.NodeVisitor):
    """Find user-accessor calls and long-lived loops inside a generator body.

    ``found`` records whether ``get_user()`` / ``current_user()`` is called
    anywhere in the walked tree; ``in_long_lived_loop`` records whether any such
    call sits inside a ``while`` / ``for`` / ``async for`` (the long-lived SSE
    pump where connect-time identity pinning becomes a staleness caveat). A bare
    user read at generator top-level (outside any loop) is treated as
    short-lived — it resolves once and the stream ends.
    """

    def __init__(self) -> None:
        self.found = False
        self.in_long_lived_loop = False
        self._loop_depth = 0

    def _visit_loop(self, node: ast.AST) -> None:
        self._loop_depth += 1
        self.generic_visit(node)
        self._loop_depth -= 1

    def visit_While(self, node: ast.While) -> None:
        self._visit_loop(node)

    def visit_For(self, node: ast.For) -> None:
        self._visit_loop(node)

    def visit_AsyncFor(self, node: ast.AsyncFor) -> None:
        self._visit_loop(node)

    def visit_Call(self, node: ast.Call) -> None:
        if _call_name(node.func) in _USER_ACCESSORS:
            self.found = True
            if self._loop_depth > 0:
                self.in_long_lived_loop = True
        self.generic_visit(node)


def _eventstream_generator_arg(handler_tree: ast.AST) -> ast.expr | None:
    """Return the single positional argument of the first ``EventStream(...)`` call.

    ``EventStream(generate())`` -> the ``generate()`` call node;
    ``EventStream(gen)`` -> the ``gen`` Name node. Returns ``None`` when no
    ``EventStream(...)`` call with a first positional arg is found.
    """
    for node in ast.walk(handler_tree):
        if not isinstance(node, ast.Call):
            continue
        if _call_name(node.func) != "EventStream":
            continue
        if node.args:
            return node.args[0]
    return None


def _generator_callable_name(gen_arg: ast.expr) -> str | None:
    """Resolve the generator-producing name from an ``EventStream(...)`` arg.

    ``generate()`` -> ``"generate"``; ``gen`` -> ``"gen"``. ``None`` for any
    other shape (e.g. an inline comprehension or a method call) — the caller
    falls back to walking the whole handler tree.
    """
    if isinstance(gen_arg, ast.Call):
        return _call_name(gen_arg.func)
    if isinstance(gen_arg, ast.Name):
        return gen_arg.id
    return None


def _find_nested_funcdef(tree: ast.AST, name: str) -> ast.AST | None:
    """Find a nested ``async def``/``def`` named *name* inside *tree*."""
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    return None


def _resolve_module_level_generator(handler: Any, name: str) -> ast.AST | None:
    """Resolve a MODULE-LEVEL generator function by *name* via ``__globals__``.

    The handler-source AST walk only sees generators defined as NESTED
    functions inside the handler. A module-level ``async def gen()`` passed as
    ``EventStream(gen())`` is NOT in the handler source — so we resolve the
    bare name against the handler's ``__globals__`` and parse THAT function's
    source. Returns ``None`` when the name is not a module-level function, or
    its source is unavailable.
    """
    target = inspect.unwrap(handler)
    glb = getattr(target, "__globals__", None)
    if not isinstance(glb, dict):
        return None
    func = glb.get(name)
    if func is None or not (inspect.isfunction(func) or inspect.ismethod(func)):
        return None
    try:
        src = inspect.getsource(inspect.unwrap(func))
        return ast.parse(textwrap.dedent(src))
    except OSError, SyntaxError, TypeError:
        return None


def _analyze_eventstream_generator(handler: Any) -> _UserReadFinder | None:
    """Return a populated :class:`_UserReadFinder` for an EventStream route's generator.

    Returns ``None`` when the route is NOT an ``EventStream`` route, or its
    source/generator cannot be statically resolved (errs toward silence). The
    generator is resolved in two scopes:

    1. NESTED — an inline ``async def generate()`` inside the handler (the common
       case). Walked directly from the handler tree.
    2. MODULE-LEVEL — a bare name passed as ``EventStream(gen())`` resolved via
       the handler's ``__globals__`` and parsed separately (see
       :func:`_resolve_module_level_generator`).

    Falls back to walking the WHOLE handler tree when the generator argument's
    shape is not a plain name/call (e.g. an inline comprehension) so an inline
    user read is still seen.
    """
    try:
        source = inspect.getsource(inspect.unwrap(handler))
        handler_tree = ast.parse(textwrap.dedent(source))
    except OSError, SyntaxError, TypeError:
        return None

    gen_arg = _eventstream_generator_arg(handler_tree)
    if gen_arg is None:
        return None  # Not an EventStream route.

    finder = _UserReadFinder()
    gen_name = _generator_callable_name(gen_arg)

    target_tree: ast.AST | None = None
    if gen_name is not None:
        target_tree = _find_nested_funcdef(handler_tree, gen_name)
        if target_tree is None:
            # Not nested — try the module-level resolution (the documented
            # cross-scope path). When that also fails, fall back to the whole
            # handler tree so an inline user read is not silently missed.
            target_tree = _resolve_module_level_generator(handler, gen_name)
    if target_tree is None:
        target_tree = handler_tree

    finder.visit(target_tree)
    return finder


def _middleware_class_names(middleware_list: list[Any]) -> set[str]:
    return {type(mw).__name__ for mw in middleware_list}


def check_sse_auth_gate(
    router: Router,
    config: Any,
    middleware_list: list[Any],
) -> list[ContractIssue]:
    """Flag an EventStream generator that reads the user with no ``AuthMiddleware``.

    An ``EventStream`` route whose generator calls ``get_user()`` /
    ``current_user()`` resolves the **connect-time-pinned** user — but only when
    ``AuthMiddleware`` is wired. Without it the captured user is ``AnonymousUser``
    for the entire stream, so an auth-sensitive SSE feed silently serves the
    anonymous view to everyone. Parallels ``auth_middleware``: env-aware (ERROR
    production / WARNING staging / silent development — the dev behavior surfaces
    locally), detected by middleware class NAME.

    SCOPE: the static AST walk resolves the generator in two scopes — an inline
    nested ``async def`` inside the handler, AND a module-level ``async def``
    passed as ``EventStream(gen())`` (resolved via the handler ``__globals__``).
    A generator built by any other indirection (a factory, a method, a value
    threaded through another call) is not statically resolvable and is silently
    skipped — errs toward silence, never a false ERROR.
    """
    issues: list[ContractIssue] = []

    if _AUTH_MIDDLEWARE in _middleware_class_names(middleware_list):
        return issues  # User resolves — nothing to flag.

    env = getattr(config, "env", "development")
    if env not in ("production", "staging"):
        return issues
    severity = Severity.ERROR if env == "production" else Severity.WARNING

    for route in getattr(router, "routes", []):
        finder = _analyze_eventstream_generator(route.handler)
        if finder is None or not finder.found:
            continue
        path = getattr(route, "path", None) or "<route>"
        issues.append(
            ContractIssue(
                severity=severity,
                category="sse_auth_gate",
                message=(
                    f"EventStream route '{path}' reads the request user "
                    "(get_user()/current_user()) inside its generator, but no "
                    f"AuthMiddleware is registered while env='{env}'. The captured "
                    "SSE user is AnonymousUser for the whole stream, so an "
                    "auth-sensitive feed silently serves the anonymous view. "
                    "Register AuthMiddleware after SessionMiddleware."
                ),
                route=path,
            )
        )

    return issues


def check_sse_context(
    router: Router,
    config: Any,
) -> list[ContractIssue]:
    """Nudge that SSE user identity is connect-time-pinned in a long-lived stream.

    POST-FIX residual guard, NOT a broken-pattern flag: reading the user inside
    an ``EventStream`` generator now WORKS (connect-time capture). This only
    surfaces the *semantic* caveat — when the user is read inside a LONG-LIVED
    loop (``while`` / ``async for`` / ``for``), the identity is pinned at connect
    and is NOT refreshed on a mid-stream logout / permission change for the life
    of the connection. WARNING (env-aware: silent development, WARNING staging /
    production); never ERROR — the pattern is correct, this is a known-semantic
    nudge for auth-sensitive long-lived streams.

    Same two-scope resolution (and the same single-indirection blind spot) as
    :func:`check_sse_auth_gate`. A short-lived top-level user read (outside any
    loop) is NOT nudged — it resolves once and the stream ends.
    """
    issues: list[ContractIssue] = []

    env = getattr(config, "env", "development")
    if env not in ("production", "staging"):
        return issues

    for route in getattr(router, "routes", []):
        finder = _analyze_eventstream_generator(route.handler)
        if finder is None or not finder.in_long_lived_loop:
            continue
        path = getattr(route, "path", None) or "<route>"
        issues.append(
            ContractIssue(
                severity=Severity.WARNING,
                category="sse_context",
                message=(
                    f"EventStream route '{path}' reads the request user "
                    "(get_user()/current_user()) inside a long-lived loop. SSE "
                    "identity is PINNED at connect time — a mid-stream logout or "
                    "permission revoke is NOT reflected for the life of the "
                    "connection. This works as designed; re-check authorization "
                    "per event (or close the stream on revoke) if the feed is "
                    "auth-sensitive."
                ),
                route=path,
            )
        )

    return issues


def _infer_emitted_events(handler: Any) -> set[str] | None:
    """Infer literal SSE event names emitted by a route handler.

    Returns ``None`` when source is unavailable or a relevant event name is
    dynamic. Dynamic cases are skipped by the cross-reference check so the
    contract errs toward silence instead of false positives.
    """
    try:
        source = inspect.getsource(inspect.unwrap(handler))
        tree = ast.parse(textwrap.dedent(source))
    except OSError, SyntaxError, TypeError:
        return None

    emitted: set[str] = set()
    saw_sse_call = False
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func_name = _call_name(node.func)
        if func_name == "SSEEvent":
            saw_sse_call = True
            confident, value = _string_kwarg(node, "event")
            if not confident:
                return None
            emitted.add(value or "message")
        elif func_name == "Fragment":
            saw_sse_call = True
            confident, value = _string_kwarg(node, "target")
            if not confident:
                return None
            emitted.add(value or "message")

    return emitted if saw_sse_call else set()


def check_sse_self_swap(template_sources: dict[str, str]) -> list[ContractIssue]:
    """Error when sse-swap appears on same element as sse-connect."""
    issues: list[ContractIssue] = []
    for template_name, source in template_sources.items():
        source = strip_template_comments(source)
        for match in _SSE_CONNECT_TAG_PATTERN.finditer(source):
            attrs_lower = match.group("attrs").lower()
            if "sse-swap" not in attrs_lower:
                continue
            swap_match = _SSE_SWAP_VALUE_PATTERN.search(match.group("attrs"))
            swap_value = swap_match.group(1) if swap_match else "?"
            issues.append(
                ContractIssue(
                    severity=Severity.ERROR,
                    category="sse_self_swap",
                    message=(
                        f'sse-swap="{swap_value}" on the same element as '
                        "sse-connect will never match. htmx uses querySelectorAll "
                        "which excludes the root element. Move sse-swap to a child element."
                    ),
                    template=template_name,
                )
            )
    return issues


def check_sse_connect_scope(
    template_sources: dict[str, str],
    broad_targets: set[str],
) -> list[ContractIssue]:
    """Warn when sse-connect is inside broad hx-target scope without mitigation."""
    if not broad_targets:
        return []
    issues: list[ContractIssue] = []
    targets_text = ", ".join(sorted(broad_targets))
    for template_name, source in template_sources.items():
        if template_name.startswith("chirp/"):
            continue
        source = strip_template_comments(source)
        for match in _SSE_CONNECT_TAG_PATTERN.finditer(source):
            attrs_lower = match.group("attrs").lower()
            if "hx-disinherit" in attrs_lower:
                continue
            if 'hx-target="this"' in attrs_lower or "hx-target='this'" in attrs_lower:
                continue
            issues.append(
                ContractIssue(
                    severity=Severity.ERROR,
                    category="sse_scope",
                    message=(
                        "sse-connect element is inside a broad hx-target scope "
                        'without mitigation. Add hx-target="this" (safe_target '
                        "middleware auto-injects this), or hx-disinherit="
                        '"hx-target hx-swap" on sse-connect. Use '
                        '{% from "chirp/sse.html" import sse_scope %} {{ sse_scope(url) }}.'
                    ),
                    template=template_name,
                    details=f"Inherited broad target(s): {targets_text}",
                )
            )
            break
    return issues


def check_sse_event_crossref(
    template_sources: dict[str, str],
    router: Router,
) -> list[ContractIssue]:
    """Cross-reference sse-swap values against declared and inferred events."""
    issues: list[ContractIssue] = []
    sse_routes: dict[str, tuple[frozenset[str], set[str] | None]] = {}
    for route in router.routes:
        contract = getattr(route.handler, "_chirp_contract", None)
        declared = frozenset()
        if contract is not None and isinstance(contract.returns, SSEContract):
            declared = contract.returns.event_types
        inferred = _infer_emitted_events(route.handler)
        if declared or inferred:
            sse_routes[route.path] = (declared, inferred)
    if not sse_routes:
        return issues

    # Pre-segment for O(1) static / O(parametric) URL matching
    route_paths = {path: frozenset() for path in sse_routes}
    static_routes, parametric_routes = build_route_index(route_paths)

    for template_name, source in template_sources.items():
        source = strip_template_comments(source)
        swap_values = extract_sse_swap_values(source)
        if not swap_values:
            continue
        for connect_match in _SSE_CONNECT_TAG_PATTERN.finditer(source):
            raw_url = connect_match.group("url")
            url = normalize_sse_url(raw_url)
            match = find_matching_route(url, static_routes, parametric_routes)
            if match is None:
                continue
            matched_route, _ = match
            declared, inferred = sse_routes[matched_route]

            known = set(declared)
            if inferred is not None:
                known.update(inferred)
            undeclared = swap_values - known
            severity = Severity.INFO if inferred is None and not declared else Severity.ERROR
            issues.extend(
                ContractIssue(
                    severity=severity,
                    category="sse_crossref",
                    message=(
                        f'sse-swap="{event_name}" listens for an event that '
                        f"route '{matched_route}' does not emit or declare. "
                        "Possible typo or missing SSEContract.event_types entry."
                    ),
                    template=template_name,
                    route=matched_route,
                    details=(
                        f"Declared event_types: {', '.join(sorted(declared)) or '(none)'}; "
                        f"Inferred event types: "
                        f"{', '.join(sorted(inferred)) if inferred is not None else '(dynamic)'}"
                    ),
                )
                for event_name in sorted(undeclared)
            )

            unlistened = set(declared) - swap_values
            issues.extend(
                ContractIssue(
                    severity=Severity.INFO,
                    category="sse_crossref",
                    message=(
                        f"SSE route '{matched_route}' declares event type "
                        f"'{event_name}' but no sse-swap in '{template_name}' "
                        "listens for it. The event may be unused or consumed elsewhere."
                    ),
                    template=template_name,
                    route=matched_route,
                )
                for event_name in sorted(unlistened)
            )
    return issues
