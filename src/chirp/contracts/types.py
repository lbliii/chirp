"""Contracts result and issue types."""

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from chirp.app.state import ContractCheckSnapshot


class ContractCheck(Protocol):
    """Protocol for custom contract check plugins.

    Both plain functions and callable class instances satisfy this
    protocol.  Register via ``app.register_contract_check()``.

    Example — function form::

        def my_check(snapshot: ContractCheckSnapshot, result: CheckResult) -> None:
            for name, source in snapshot.template_sources.items():
                if "TODO" in source:
                    result.issues.append(
                        ContractIssue(Severity.WARNING, "todo", f"TODO in {name}", template=name)
                    )

    Example — class form::

        class ComponentCheck:
            def __call__(self, snapshot: ContractCheckSnapshot, result: CheckResult) -> None:
                ...
    """

    def __call__(self, snapshot: ContractCheckSnapshot, result: CheckResult) -> None: ...


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


@dataclass(frozen=True, slots=True)
class ContractCoverage:
    """High-level coverage counters for serious hypermedia apps."""

    post_routes: int = 0
    post_routes_with_form_contract: int = 0
    mounted_page_routes: int = 0
    mounted_page_routes_with_contract: int = 0
    page_shell_contracts: int = 0
    page_shell_required_blocks: int = 0
    fragment_targets_registered: int = 0
    oob_regions_registered: int = 0
    webmcp_projections_declared: int = 0
    webmcp_projections_compiled: int = 0
    webmcp_parameters_declared: int = 0

    @property
    def post_routes_without_form_contract(self) -> int:
        """POST routes that do not declare a FormContract."""
        return max(0, self.post_routes - self.post_routes_with_form_contract)

    @property
    def mounted_page_routes_without_contract(self) -> int:
        """Mounted page routes whose handlers do not carry any route contract."""
        return max(0, self.mounted_page_routes - self.mounted_page_routes_with_contract)


@dataclass(slots=True)
class CheckResult:
    """Result of a hypermedia surface check."""

    issues: list[ContractIssue] = field(default_factory=list)
    routes_checked: int = 0
    templates_scanned: int = 0
    targets_found: int = 0
    hx_targets_validated: int = 0
    commandfor_validated: int = 0
    dead_templates_found: int = 0
    sse_fragments_validated: int = 0
    forms_validated: int = 0
    component_calls_validated: int = 0
    page_context_warnings: int = 0
    elapsed_ms: float | None = None
    coverage: ContractCoverage = field(default_factory=ContractCoverage)

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
        if self.commandfor_validated:
            extras.append(f"{self.commandfor_validated} commandfor target(s) validated")
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
        if self.elapsed_ms is not None:
            extras.append(f"{self.elapsed_ms:.1f}ms elapsed")
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
