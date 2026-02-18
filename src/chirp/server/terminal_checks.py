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

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from chirp.contracts import CheckResult, ContractIssue, Severity

# Banner width — matches terminal_errors._BANNER_WIDTH
_W = 65


# ---------------------------------------------------------------------------
# ANSI helpers
# ---------------------------------------------------------------------------


def _use_color(stream: object | None = None) -> bool:
    """True if the output stream supports ANSI color."""
    s = stream or sys.stderr
    try:
        return s.isatty()  # type: ignore[union-attr]
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
            return f"{c.red}{c.bold}\u2717{c.reset}"   # ✗
        case Severity.WARNING:
            return f"{c.yellow}\u25b2{c.reset}"         # ▲
        case Severity.INFO:
            return f"{c.dim}\u00b7{c.reset}"            # ·


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


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def format_check_result(
    result: CheckResult,
    *,
    color: bool | None = None,
) -> str:
    """Format a CheckResult for rich terminal display.

    Args:
        result: The check result to format.
        color: Force color on/off.  ``None`` auto-detects from stderr.

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
    lines.append(
        f"  {c.dim}\u2500\u2500{c.reset} {title} "
        f"{c.dim}{'\u2500' * max(pad, 1)}{c.reset}"
    )
    lines.append("")

    # ── Stats ───────────────────────────────────────────────
    sep = f" {c.dim}\u00b7{c.reset} "
    stats_parts: list[str] = []
    if result.routes_checked:
        stats_parts.append(
            f"{c.bold}{result.routes_checked}{c.reset} "
            f"{c.dim}routes{c.reset}"
        )
    if result.templates_scanned:
        stats_parts.append(
            f"{c.bold}{result.templates_scanned}{c.reset} "
            f"{c.dim}templates{c.reset}"
        )
    if result.targets_found:
        stats_parts.append(
            f"{c.bold}{result.targets_found}{c.reset} "
            f"{c.dim}targets{c.reset}"
        )
    if result.hx_targets_validated:
        stats_parts.append(
            f"{c.bold}{result.hx_targets_validated}{c.reset} "
            f"{c.dim}hx-target selectors{c.reset}"
        )
    if stats_parts:
        lines.append(f"  {sep.join(stats_parts)}")
        lines.append("")

    # ── Issues (errors first, then warnings, then info) ─────
    errors = [i for i in result.issues if i.severity == Severity.ERROR]
    warnings = [i for i in result.issues if i.severity == Severity.WARNING]
    infos = [i for i in result.issues if i.severity == Severity.INFO]

    for issue_group in (errors, warnings, infos):
        for issue in issue_group:
            lines.extend(_format_issue(issue, c))
            lines.append("")  # blank line between issues

    # ── Summary line ────────────────────────────────────────
    if not errors and not warnings:
        lines.append(
            f"  {c.green}{c.bold}\u2713{c.reset}  "
            f"{c.green}All clear{c.reset}"
        )
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
