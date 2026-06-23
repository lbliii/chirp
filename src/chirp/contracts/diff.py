"""Hypermedia contract diff — compare two serialized check results."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class ContractDiff:
    """Added and removed contract issues between two check runs."""

    added: tuple[dict[str, Any], ...]
    removed: tuple[dict[str, Any], ...]

    @property
    def has_changes(self) -> bool:
        return bool(self.added or self.removed)

    @property
    def added_errors(self) -> tuple[dict[str, Any], ...]:
        return tuple(i for i in self.added if i.get("severity") == "error")

    @property
    def added_warnings(self) -> tuple[dict[str, Any], ...]:
        return tuple(i for i in self.added if i.get("severity") == "warning")

    def summary_lines(self) -> list[str]:
        """Human-readable diff summary for terminal output."""
        lines = ["Hypermedia surface change:"]
        lines.extend(f"  + {self._format_issue_line(issue)}" for issue in self.added)
        lines.extend(f"  - {self._format_issue_line(issue)}" for issue in self.removed)
        if not self.has_changes:
            lines.append("  (no issue changes)")
        return lines

    @staticmethod
    def _format_issue_line(issue: dict[str, Any]) -> str:
        sev = issue.get("severity", "?")
        loc = ""
        if issue.get("template"):
            loc = f" in {issue['template']}"
        elif issue.get("route"):
            loc = f" on {issue['route']}"
        return f"[{sev}] {issue.get('category', '?')}: {issue.get('message', '')}{loc}"

    def markdown_comment(
        self,
        *,
        app: str,
        base_ref: str,
        issue_number: int = 344,
    ) -> str:
        """GitHub PR comment body for a hypermedia contract diff."""
        marker = "<!-- chirp-contract-diff -->"
        lines = [
            marker,
            f"## Hypermedia surface change (`{app}` vs `{base_ref}`)",
            "",
        ]
        if not self.has_changes:
            lines.append("_No contract issue changes._")
        else:
            if self.added:
                lines.append("**Added**")
                lines.extend(f"- `{self._format_issue_line(issue)}`" for issue in self.added)
                lines.append("")
            if self.removed:
                lines.append("**Removed**")
                lines.extend(f"- `{self._format_issue_line(issue)}`" for issue in self.removed)
                lines.append("")
        if self.added_errors:
            lines.append(
                f"> **{len(self.added_errors)} new contract error(s).** Review before merge."
            )
        elif self.added_warnings:
            lines.append(f"> {len(self.added_warnings)} new contract warning(s).")
        lines.extend(
            [
                "",
                f"_Automated by [`chirp diff`](https://github.com/lbliii/chirp/issues/{issue_number}). "
                "New contract ERRORs block merge; new warnings are advisory._",
            ]
        )
        return "\n".join(lines)


def _issue_key(issue: dict[str, Any]) -> tuple[str, str, str, str, str]:
    return (
        str(issue.get("severity", "")),
        str(issue.get("category", "")),
        str(issue.get("route") or ""),
        str(issue.get("template") or ""),
        str(issue.get("message", "")),
    )


def diff_contract_dicts(
    baseline: dict[str, Any],
    current: dict[str, Any],
) -> ContractDiff:
    """Diff two serialized :func:`~chirp.contracts.serialize.result_to_dict` payloads."""
    base_issues = {_issue_key(i): i for i in baseline.get("issues", [])}
    curr_issues = {_issue_key(i): i for i in current.get("issues", [])}
    added_keys = set(curr_issues) - set(base_issues)
    removed_keys = set(base_issues) - set(curr_issues)
    added = tuple(curr_issues[k] for k in sorted(added_keys))
    removed = tuple(base_issues[k] for k in sorted(removed_keys))
    return ContractDiff(added=added, removed=removed)
