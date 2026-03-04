"""Contracts result and issue types."""

from dataclasses import dataclass, field
from enum import Enum


class Severity(Enum):
    """Severity of a contract validation issue."""

    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass(frozen=True, slots=True)
class ContractIssue:
    """A single validation issue found during contract checking."""

    severity: Severity
    category: str
    message: str
    template: str | None = None
    route: str | None = None
    details: str | None = None


@dataclass(slots=True)
class CheckResult:
    """Result of a hypermedia surface check."""

    issues: list[ContractIssue] = field(default_factory=list)
    routes_checked: int = 0
    templates_scanned: int = 0
    targets_found: int = 0
    hx_targets_validated: int = 0
    dead_templates_found: int = 0
    sse_fragments_validated: int = 0
    forms_validated: int = 0
    component_calls_validated: int = 0
    page_context_warnings: int = 0

    @property
    def errors(self) -> list[ContractIssue]:
        return [i for i in self.issues if i.severity == Severity.ERROR]

    @property
    def warnings(self) -> list[ContractIssue]:
        return [i for i in self.issues if i.severity == Severity.WARNING]

    @property
    def ok(self) -> bool:
        return not self.errors

    def summary(self) -> str:
        lines = [
            f"Checked {self.routes_checked} routes, "
            f"scanned {self.templates_scanned} templates, "
            f"found {self.targets_found} hypermedia targets, "
            f"validated {self.hx_targets_validated} hx-target selectors.",
        ]
        extras: list[str] = []
        if self.dead_templates_found:
            extras.append(f"{self.dead_templates_found} dead template(s)")
        if self.sse_fragments_validated:
            extras.append(f"{self.sse_fragments_validated} SSE fragment(s) validated")
        if self.forms_validated:
            extras.append(f"{self.forms_validated} form(s) validated")
        if self.component_calls_validated:
            extras.append(f"{self.component_calls_validated} component call(s) validated")
        if self.page_context_warnings:
            extras.append(f"{self.page_context_warnings} Page context warning(s)")
        if extras:
            lines.append(", ".join(extras) + ".")
        if self.ok and not self.warnings:
            lines.append("No issues found.")
        elif self.ok:
            lines.append(f"No errors. {len(self.warnings)} warning(s).")
        else:
            lines.append(f"{len(self.errors)} error(s), {len(self.warnings)} warning(s).")
        for issue in self.issues:
            prefix = issue.severity.value.upper()
            loc = f" in {issue.template}" if issue.template else ""
            lines.append(f"  [{prefix}] {issue.message}{loc}")
            if issue.details:
                lines.append(f"           {issue.details}")
        return "\n".join(lines)
