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


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def format_check_result(
    result: CheckResult,
    *,
    color: bool | None = None,
    fragment_target_registry: FragmentTargetRegistry | None = None,
    verbose_registry: bool = False,
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
    if stats_parts:
        lines.append(f"  {sep.join(stats_parts)}")
        lines.append("")

    # ── Issues (errors first, then warnings, then info) ─────
    by_severity: dict[Any, list[Any]] = defaultdict(list)
    for i in result.issues:
        by_severity[i.severity].append(i)
    errors = by_severity[Severity.ERROR]
    warnings = by_severity[Severity.WARNING]
    infos = by_severity[Severity.INFO]

    route_shown = False
    for issue_group in (errors, warnings, infos):
        if (
            any(getattr(i, "category", "") == "route_contract" for i in issue_group)
            and not route_shown
        ):
            lines.append(f"  {c.cyan}Route contract{c.reset}")
            lines.append("")
            route_shown = True
        for issue in issue_group:
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
