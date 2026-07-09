"""Tests for chirp.server.terminal_checks fragment-target formatting."""

from __future__ import annotations

import pytest

from chirp.contracts import CheckResult, ContractIssue, Severity
from chirp.server.terminal_checks import _concern_for_category, format_check_result
from chirp.templating.fragment_target_registry import (
    FragmentTargetRegistry,
    PageShellContract,
    PageShellTarget,
)


def _strip_ansi(text: str) -> str:
    import re

    return re.sub(r"\x1b\[[0-9;]*m", "", text)


def _registry_with(*contracts: PageShellContract) -> FragmentTargetRegistry:
    registry = FragmentTargetRegistry()
    for contract in contracts:
        registry.register_contract(contract)
    return registry


SAMPLE_CONTRACT = PageShellContract(
    name="chirpui_page_shell",
    targets=(
        PageShellTarget(
            target_id="main",
            fragment_block="page_root",
            triggers_shell_update=False,
            required=True,
            omit_outer_layouts=True,
        ),
        PageShellTarget(
            target_id="page-root",
            fragment_block="page_root_inner",
            triggers_shell_update=True,
            required=True,
        ),
    ),
)


class TestFormatterWithEmptyRegistry:
    def test_empty_registry_adds_no_stats_line(self) -> None:
        registry = FragmentTargetRegistry()
        out = _strip_ansi(
            format_check_result(CheckResult(), fragment_target_registry=registry, color=False)
        )
        assert "fragment target" not in out.lower()

    def test_no_registry_matches_original_behavior(self) -> None:
        out = _strip_ansi(format_check_result(CheckResult(), color=False))
        assert "fragment target" not in out.lower()


class TestFormatterStatsLine:
    def test_stats_line_reports_registered_count_singular(self) -> None:
        contract = PageShellContract(
            name="shell",
            targets=(PageShellTarget(target_id="only", fragment_block="only_block"),),
        )
        registry = _registry_with(contract)
        out = _strip_ansi(
            format_check_result(CheckResult(), fragment_target_registry=registry, color=False)
        )
        assert "1 fragment target registered" in out

    def test_stats_line_reports_registered_count_plural(self) -> None:
        registry = _registry_with(SAMPLE_CONTRACT)
        out = _strip_ansi(
            format_check_result(CheckResult(), fragment_target_registry=registry, color=False)
        )
        assert "2 fragment targets registered" in out


class TestFormatterVerboseDump:
    def test_verbose_dump_includes_contract_name(self) -> None:
        registry = _registry_with(SAMPLE_CONTRACT)
        out = _strip_ansi(
            format_check_result(
                CheckResult(),
                fragment_target_registry=registry,
                verbose_registry=True,
                color=False,
            )
        )
        assert "chirpui_page_shell" in out
        assert "Fragment targets" in out

    def test_verbose_dump_shows_every_target(self) -> None:
        registry = _registry_with(SAMPLE_CONTRACT)
        out = _strip_ansi(
            format_check_result(
                CheckResult(),
                fragment_target_registry=registry,
                verbose_registry=True,
                color=False,
            )
        )
        assert "#main" in out
        assert "page_root" in out
        assert "#page-root" in out
        assert "page_root_inner" in out

    def test_verbose_dump_shows_flag_state(self) -> None:
        registry = _registry_with(SAMPLE_CONTRACT)
        out = _strip_ansi(
            format_check_result(
                CheckResult(),
                fragment_target_registry=registry,
                verbose_registry=True,
                color=False,
            )
        )
        assert "shell:no" in out
        assert "shell:yes" in out
        assert "outer:skip" in out
        assert "outer:keep" in out

    def test_verbose_dump_groups_unscoped_targets(self) -> None:
        registry = FragmentTargetRegistry()
        registry.register("standalone", fragment_block="standalone_block")
        out = _strip_ansi(
            format_check_result(
                CheckResult(),
                fragment_target_registry=registry,
                verbose_registry=True,
                color=False,
            )
        )
        assert "unscoped" in out
        assert "#standalone" in out

    def test_non_verbose_skips_dump(self) -> None:
        registry = _registry_with(SAMPLE_CONTRACT)
        out = _strip_ansi(
            format_check_result(
                CheckResult(),
                fragment_target_registry=registry,
                verbose_registry=False,
                color=False,
            )
        )
        assert "#main" not in out
        assert "page_root" not in out
        assert "2 fragment targets registered" in out


class TestFormatterConcernGroups:
    @pytest.mark.parametrize(
        ("category", "concern"),
        [
            ("page_handlers", "Routing"),
            ("route_names", "Routing"),
            ("query_target", "Routing"),
            ("hx-target", "HTMX"),
            ("hx-indicator", "HTMX"),
            ("hx-boost", "HTMX"),
            ("csrf_form", "Forms"),
            ("security_stack", "Production Safety"),
            ("query_cors", "Production Safety"),
            ("mount_app_merge", "Setup"),
        ],
    )
    def test_public_contract_categories_have_specific_groups(
        self, category: str, concern: str
    ) -> None:
        assert _concern_for_category(category) == concern

    def test_groups_issues_by_contract_concern(self) -> None:
        result = CheckResult(
            issues=[
                ContractIssue(
                    Severity.WARNING,
                    "a11y_label",
                    "<input> has no label",
                    template="form.html",
                ),
                ContractIssue(
                    Severity.ERROR,
                    "route_contract",
                    "route metadata is invalid",
                    route="/docs",
                ),
                ContractIssue(
                    Severity.INFO,
                    "form_contract",
                    "form has no contract",
                    template="form.html",
                    route="/submit",
                ),
            ]
        )
        out = _strip_ansi(format_check_result(result, color=False))

        assert "Routing" in out
        assert "Accessibility" in out
        assert "Forms" in out
        assert out.index("Routing") < out.index("Forms") < out.index("Accessibility")

    def test_elapsed_time_is_shown_in_stats(self) -> None:
        result = CheckResult(routes_checked=2, templates_scanned=3, elapsed_ms=12.345)
        out = _strip_ansi(format_check_result(result, color=False))
        assert "12.3ms elapsed" in out

    def test_coverage_block_is_optional(self) -> None:
        result = CheckResult()
        without = _strip_ansi(format_check_result(result, color=False))
        with_coverage = _strip_ansi(format_check_result(result, color=False, show_coverage=True))
        assert "Coverage" not in without
        assert "Coverage" in with_coverage
        assert "POST FormContract" in with_coverage
        assert "WebMCP projections" in with_coverage
