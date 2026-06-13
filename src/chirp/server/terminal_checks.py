"""Rich terminal formatting for hypermedia surface checks.

Produces structured, colored output for contract validation results
that appear at startup in debug mode.  Respects TTY detection — no
ANSI codes when piped or redirected.

Matches the visual language of pounce's startup banner (``->`` arrows,
clean indentation) and chirp's terminal error formatting (dash banners,
compact diagnostics).

Example output (with color)::

    ── chirp check ─────────────────────────────────────────────

      5 routes · 3 templates · 12 targets · 8 hx-target selectors

      ▲  hx-target="#main" — no element with id="main" found
         in pokedex.html
         Did you mean "#mainn"?

      ✓  No errors · 1 warning

    ─────────────────────────────────────────────────────────────

"""

import sys
from collections import defaultdict
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from chirp.contracts import CheckResult, ContractIssue, Severity
    from chirp.templating.fragment_target_registry import FragmentTargetRegistry

# Banner width — matches terminal_errors._BANNER_WIDTH
_W = 65


# ---------------------------------------------------------------------------
# ANSI helpers
# ---------------------------------------------------------------------------


def _use_color(stream: object | None = None) -> bool:
    """True if the output stream supports ANSI color."""
    s = stream or sys.stderr
    try:
        return s.isatty()  # type: ignore[union-attr]  # ty: ignore[unresolved-attribute]
    except Exception:
        return False


class _Palette:
    """ANSI escape sequences — empty strings when color is disabled."""

    __slots__ = (
        "blue",
        "bold",
        "cyan",
        "dim",
        "green",
        "magenta",
        "red",
        "reset",
        "yellow",
    )

    def __init__(self, *, enabled: bool) -> None:
        if enabled:
            self.reset = "\033[0m"
            self.bold = "\033[1m"
            self.dim = "\033[2m"
            self.red = "\033[31m"
            self.green = "\033[32m"
            self.yellow = "\033[33m"
            self.blue = "\033[34m"
            self.cyan = "\033[36m"
            self.magenta = "\033[35m"
        else:
            self.reset = ""
            self.bold = ""
            self.dim = ""
            self.red = ""
            self.green = ""
            self.yellow = ""
            self.blue = ""
            self.cyan = ""
            self.magenta = ""


# ---------------------------------------------------------------------------
# Issue formatting
# ---------------------------------------------------------------------------


def _severity_icon(severity: Severity, c: _Palette) -> str:
    """Colored icon for an issue severity."""
    from chirp.contracts import Severity

    match severity:
        case Severity.ERROR:
            return f"{c.red}{c.bold}\u2717{c.reset}"  # ✗
        case Severity.WARNING:
            return f"{c.yellow}\u25b2{c.reset}"  # ▲
        case Severity.INFO:
            return f"{c.dim}\u00b7{c.reset}"  # ·


def _format_issue(issue: ContractIssue, c: _Palette) -> list[str]:
    """Format a single issue as indented lines."""
    icon = _severity_icon(issue.severity, c)
    lines: list[str] = []

    # Main message
    lines.append(f"  {icon}  {c.bold}{issue.message}{c.reset}")

    # Template location
    if issue.template:
        lines.append(f"     {c.dim}in{c.reset} {c.cyan}{issue.template}{c.reset}")

    # Route
    if issue.route:
        lines.append(f"     {c.dim}route{c.reset} {issue.route}")

    # Details (fuzzy suggestion, available IDs, etc.)
    if issue.details:
        lines.append(f"     {c.dim}{issue.details}{c.reset}")

    return lines


_CONCERN_ORDER: tuple[str, ...] = (
    "Setup",
    "Routing",
    "Templates",
    "HTMX",
    "OOB / Suspense / SSE",
    "Forms",
    "Layouts",
    "Accessibility",
    "Components",
    "Reactive",
    "Shapes",
    "Production Safety",
    "Plugins",
    "Docs",
    "Other",
)

_CATEGORY_CONCERNS: dict[str, str] = {
    # Setup / routing
    "setup": "Setup",
    "routing": "Routing",
    "route": "Routing",
    "route_contract": "Routing",
    "page_handlers": "Routing",
    "route_names": "Routing",
    "method": "Routing",
    "target": "Routing",
    "orphan": "Routing",
    "htmx_partial": "Routing",
    # Templates
    "template_contract": "Templates",
    "inline_template": "Templates",
    "dead": "Templates",
    "component": "Components",
    "page_context": "Templates",
    "unreachable_block": "Templates",
    "context_cascade": "Templates",
    "composition_extends": "Templates",
    "boundary": "Templates",
    "macro_css": "Templates",
    # HTMX / browser wiring
    "hx-target": "HTMX",
    "hx-indicator": "HTMX",
    "hx-boost": "HTMX",
    "selector_syntax": "HTMX",
    "swap_safety": "HTMX",
    "select_inheritance": "HTMX",
    "view_transition_scope": "HTMX",
    "vary": "HTMX",
    "command": "HTMX",
    "commandfor": "HTMX",
    "alpine_cdn_url": "HTMX",
    "htmx_provisioned": "HTMX",
    "islands": "HTMX",
    "fragment_island": "HTMX",
    # Streaming / OOB
    "fragment": "OOB / Suspense / SSE",
    "fragment_target_orphan": "OOB / Suspense / SSE",
    "oob_target": "OOB / Suspense / SSE",
    "oob_registry": "OOB / Suspense / SSE",
    "defer_falsy": "OOB / Suspense / SSE",
    "sse": "OOB / Suspense / SSE",
    "sse_self_swap": "OOB / Suspense / SSE",
    "sse_scope": "OOB / Suspense / SSE",
    "sse_crossref": "OOB / Suspense / SSE",
    "live_block_unknown": "OOB / Suspense / SSE",
    "live_block_unreachable_route": "OOB / Suspense / SSE",
    "signal_dead_binding": "OOB / Suspense / SSE",
    "signal_orphan": "OOB / Suspense / SSE",
    # Forms / layouts / accessibility
    "form": "Forms",
    "form_contract": "Forms",
    "csrf_form": "Forms",
    "layout_chain": "Layouts",
    "layout_outlet": "Layouts",
    "layout_frame": "Layouts",
    "page_shell": "Layouts",
    "a11y_interactive": "Accessibility",
    "a11y_label": "Accessibility",
    "a11y_alt": "Accessibility",
    "a11y_heading": "Accessibility",
    "a11y_landmark": "Accessibility",
    # Runtime systems
    "reactive_block": "Reactive",
    "reactive_cycle": "Reactive",
    "reactive_paths": "Reactive",
    "reactive_audience": "Reactive",
    # Verified Shapes
    "shapecheck": "Shapes",
    # Safety / plugins / docs
    "sse_speculation": "Production Safety",
    "csrf_session": "Production Safety",
    "security_stack": "Production Safety",
    "static_streaming": "Production Safety",
    "middleware_signature": "Production Safety",
    "secret_key": "Production Safety",
    "mount_app_merge": "Setup",
    "plugin_check_error": "Plugins",
    "chirpui_import": "Plugins",
    "chirpui_runtime": "Plugins",
    "design_system": "Plugins",
    "blog": "Plugins",
    "docs_parse": "Docs",
    "docs_duplicate_slug": "Docs",
    "docs_cross_ref": "Docs",
    "docs_draft_exposed": "Docs",
}


def _concern_for_category(category: str) -> str:
    """Return the terminal output group for a contract category."""
    return _CATEGORY_CONCERNS.get(category, "Other")


def _group_issues_by_concern(issues: list[ContractIssue]) -> list[tuple[str, list[ContractIssue]]]:
    grouped: dict[str, list[ContractIssue]] = {name: [] for name in _CONCERN_ORDER}
    for issue in issues:
        grouped[_concern_for_category(issue.category)].append(issue)
    return [(name, grouped[name]) for name in _CONCERN_ORDER if grouped[name]]


def _format_fragment_registry(
    registry: FragmentTargetRegistry,
    c: _Palette,
) -> list[str]:
    """Render the fragment target registry grouped by contract.

    Returns a list of lines or an empty list when the registry has no
    registered targets.
    """
    all_ids = sorted(registry.registered_targets)
    if not all_ids:
        return []

    contracts = registry.registered_contracts
    contract_target_ids: set[str] = set()
    groups: list[tuple[str, list[tuple[str, Any]]]] = []
    for contract in contracts:
        rows: list[tuple[str, Any]] = []
        for target in contract.targets:
            tid = target.target_id.lstrip("#")
            contract_target_ids.add(tid)
            config = registry.get(tid)
            if config is not None:
                rows.append((tid, config))
        if rows:
            groups.append((contract.name, rows))

    unscoped_rows: list[tuple[str, Any]] = []
    for tid in all_ids:
        if tid in contract_target_ids:
            continue
        config = registry.get(tid)
        if config is not None:
            unscoped_rows.append((tid, config))
    if unscoped_rows:
        groups.append(("unscoped", unscoped_rows))

    if not groups:
        return []

    id_width = max(len(f"#{tid}") for tid, _ in (r for _, rows in groups for r in rows))
    block_width = max(len(cfg.fragment_block) for _, rows in groups for _, cfg in rows)

    lines: list[str] = []
    lines.append(f"  {c.cyan}Fragment targets{c.reset}")
    lines.append("")
    for group_name, rows in groups:
        header = group_name if group_name != "unscoped" else "unscoped"
        lines.append(f"  {c.bold}{header}{c.reset} {c.dim}({len(rows)}){c.reset}")
        for tid, cfg in rows:
            shell = "yes" if cfg.triggers_shell_update else "no"
            outer = "skip" if cfg.omit_outer_layouts else "keep"
            required = "required" if cfg.required else "optional"
            lines.append(
                f"    {c.cyan}#{tid}{c.reset}{' ' * (id_width - len(tid) - 1)}"
                f"  {c.dim}\u2192{c.reset}  "
                f"{cfg.fragment_block}{' ' * (block_width - len(cfg.fragment_block))}"
                f"  {c.dim}shell:{c.reset}{shell}"
                f"  {c.dim}outer:{c.reset}{outer}"
                f"  {c.dim}{required}{c.reset}"
            )
        lines.append("")
    return lines[:-1] if lines[-1] == "" else lines


def _format_coverage(result: CheckResult, c: _Palette) -> list[str]:
    """Render high-level contract coverage counters."""
    coverage = result.coverage
    lines = [f"  {c.cyan}Coverage{c.reset}", ""]
    rows = (
        (
            "POST FormContract",
            coverage.post_routes_with_form_contract,
            coverage.post_routes,
            coverage.post_routes_without_form_contract,
        ),
        (
            "Mounted page contracts",
            coverage.mounted_page_routes_with_contract,
            coverage.mounted_page_routes,
            coverage.mounted_page_routes_without_contract,
        ),
    )
    for label, covered, total, missing in rows:
        if total == 0:
            lines.append(f"  {label}: {c.dim}n/a{c.reset}")
            continue
        status = f"{covered}/{total}"
        suffix = "" if missing == 0 else f" {c.dim}({missing} uncovered){c.reset}"
        lines.append(f"  {label}: {c.bold}{status}{c.reset}{suffix}")
    lines.append(
        f"  Page shell contracts: {c.bold}{coverage.page_shell_contracts}{c.reset}"
        f" {c.dim}({coverage.page_shell_required_blocks} required block"
        f"{'s' if coverage.page_shell_required_blocks != 1 else ''}){c.reset}"
    )
    lines.append(
        f"  Fragment targets: {c.bold}{coverage.fragment_targets_registered}{c.reset}"
        f" {c.dim}registered{c.reset}"
    )
    lines.append(
        f"  OOB regions: {c.bold}{coverage.oob_regions_registered}{c.reset}"
        f" {c.dim}registered{c.reset}"
    )
    return lines


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def format_check_result(
    result: CheckResult,
    *,
    color: bool | None = None,
    fragment_target_registry: FragmentTargetRegistry | None = None,
    verbose_registry: bool = False,
    show_coverage: bool = False,
) -> str:
    """Format a CheckResult for rich terminal display.

    Args:
        result: The check result to format.
        color: Force color on/off.  ``None`` auto-detects from stderr.
        fragment_target_registry: If provided and non-empty, a summary of
            registered fragment targets is included — one stats entry for
            contract count, and (when ``verbose_registry`` is True) a full
            dump grouped by contract before the summary line.
        verbose_registry: When True, render the full registry dump. Gated
            by the caller on ``config.debug``.
        show_coverage: When True, render route/template coverage counters
            that make form, mounted-page, shell, and OOB contract coverage visible.

    Returns:
        Multi-line string ready for ``sys.stderr.write()``.
    """
    from chirp.contracts import Severity

    use = color if color is not None else _use_color()
    c = _Palette(enabled=use)

    lines: list[str] = []
    rule = f"{c.dim}\u2500{c.reset}" * _W

    # ── Header ──────────────────────────────────────────────
    title = f"{c.bold}chirp check{c.reset}"
    # Build the title rule manually so ANSI codes don't affect width
    title_text = "chirp check"
    pad = _W - len(title_text) - 4  # 4 = "── " + " "
    lines.append(f"  {c.dim}\u2500\u2500{c.reset} {title} {c.dim}{'\u2500' * max(pad, 1)}{c.reset}")
    lines.append("")

    # ── Stats ───────────────────────────────────────────────
    sep = f" {c.dim}\u00b7{c.reset} "
    stats_parts: list[str] = []
    if result.routes_checked:
        stats_parts.append(f"{c.bold}{result.routes_checked}{c.reset} {c.dim}routes{c.reset}")
    if result.templates_scanned:
        stats_parts.append(f"{c.bold}{result.templates_scanned}{c.reset} {c.dim}templates{c.reset}")
    if result.targets_found:
        stats_parts.append(f"{c.bold}{result.targets_found}{c.reset} {c.dim}targets{c.reset}")
    if result.hx_targets_validated:
        stats_parts.append(
            f"{c.bold}{result.hx_targets_validated}{c.reset} {c.dim}hx-target selectors{c.reset}"
        )
    if fragment_target_registry is not None:
        n_registered = len(fragment_target_registry.registered_targets)
        if n_registered:
            noun = "fragment target" if n_registered == 1 else "fragment targets"
            stats_parts.append(f"{c.bold}{n_registered}{c.reset} {c.dim}{noun} registered{c.reset}")
    if result.elapsed_ms is not None:
        stats_parts.append(f"{c.bold}{result.elapsed_ms:.1f}ms{c.reset} {c.dim}elapsed{c.reset}")
    if stats_parts:
        lines.append(f"  {sep.join(stats_parts)}")
        lines.append("")

    if show_coverage:
        lines.extend(_format_coverage(result, c))
        lines.append("")

    # ── Issues grouped by concern, severity within concern ──
    by_severity: dict[Any, list[Any]] = defaultdict(list)
    for i in result.issues:
        by_severity[i.severity].append(i)
    errors = by_severity[Severity.ERROR]
    warnings = by_severity[Severity.WARNING]
    infos = by_severity[Severity.INFO]

    ordered_issues = [*errors, *warnings, *infos]
    for concern, issue_group in _group_issues_by_concern(ordered_issues):
        lines.append(f"  {c.cyan}{concern}{c.reset}")
        lines.append("")
        for severity_group in (Severity.ERROR, Severity.WARNING, Severity.INFO):
            severity_issues = [i for i in issue_group if i.severity == severity_group]
            for issue in severity_issues:
                lines.extend(_format_issue(issue, c))
                lines.append("")

    # ── Fragment target registry dump (verbose only) ────────
    if verbose_registry and fragment_target_registry is not None:
        reg_lines = _format_fragment_registry(fragment_target_registry, c)
        if reg_lines:
            lines.extend(reg_lines)
            lines.append("")

    # ── Summary line ────────────────────────────────────────
    if not errors and not warnings:
        lines.append(f"  {c.green}{c.bold}\u2713{c.reset}  {c.green}All clear{c.reset}")
    elif not errors:
        lines.append(
            f"  {c.green}{c.bold}\u2713{c.reset}  "
            f"{c.green}No errors{c.reset}"
            f" {c.dim}\u00b7{c.reset} "
            f"{c.yellow}{len(warnings)} warning{'s' if len(warnings) != 1 else ''}"
            f"{c.reset}"
        )
    else:
        lines.append(
            f"  {c.red}{c.bold}\u2717{c.reset}  "
            f"{c.red}{len(errors)} error{'s' if len(errors) != 1 else ''}{c.reset}"
            f" {c.dim}\u00b7{c.reset} "
            f"{c.yellow}{len(warnings)} warning{'s' if len(warnings) != 1 else ''}"
            f"{c.reset}"
        )

    # ── Footer rule ─────────────────────────────────────────
    lines.append("")
    lines.append(f"  {rule}")
    lines.append("")

    return "\n".join(lines)
