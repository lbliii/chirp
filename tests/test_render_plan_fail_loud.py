"""Tests for the zero-silent-failure policy on OOB region rendering.

Before: render_plan.py swallowed any exception from adapter.render_block for
region updates and substituted html = "", producing empty OOB swaps that
wiped existing DOM content.

After: non-existent blocks raise BlockNotFoundError unless the region is
registered with optional=True, in which case the region is silently dropped
(not emitted with an empty body).
"""

from pathlib import Path

import pytest
from kida import Environment, FileSystemLoader

from chirp.errors import BlockNotFoundError
from chirp.templating.composition import RegionUpdate, ViewRef
from chirp.templating.kida_adapter import KidaAdapter
from chirp.templating.oob_registry import OOBRegionConfig, OOBRegistry
from chirp.templating.render_plan import (
    RenderPlan,
    execute_render_plan,
    serialize_rendered_plan,
)

TEMPLATES_DIR = Path(__file__).parent / "templates"


@pytest.fixture
def kida_env() -> Environment:
    return Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)))


def _plan_with_region_update(view: ViewRef, region: str = "sidebar") -> RenderPlan:
    """Build a minimal render plan containing a single region update."""
    return RenderPlan(
        intent="page_fragment",
        main_view=ViewRef(
            template="oob_layout/page.html",
            block="content",
            context={},
        ),
        region_updates=(RegionUpdate(region=region, view=view),),
    )


class TestNonOptionalRegionRaises:
    def test_missing_block_raises_block_not_found_error(self, kida_env: Environment) -> None:
        """A region update referencing a non-existent block raises BlockNotFoundError
        when the region is not registered as optional."""
        adapter = KidaAdapter(kida_env)
        reg = OOBRegistry()
        # Registered but not marked optional; layout is missing this block
        reg.register(
            "does_not_exist_oob",
            OOBRegionConfig(target_id="missing-target"),
        )

        plan = _plan_with_region_update(
            ViewRef(
                template="oob_layout/_layout.html",
                block="does_not_exist_oob",
                context={},
            ),
            region="missing-target",
        )
        with pytest.raises(BlockNotFoundError) as excinfo:
            execute_render_plan(plan, adapter=adapter, oob_registry=reg)
        assert excinfo.value.template == "oob_layout/_layout.html"
        assert excinfo.value.block == "does_not_exist_oob"
        assert excinfo.value.region == "missing-target"

    def test_unregistered_missing_block_also_raises(self, kida_env: Environment) -> None:
        """Region updates without a registry config default to non-optional."""
        adapter = KidaAdapter(kida_env)
        plan = _plan_with_region_update(
            ViewRef(
                template="oob_layout/_layout.html",
                block="unregistered_missing_oob",
                context={},
            ),
            region="ghost",
        )
        with pytest.raises(BlockNotFoundError):
            execute_render_plan(plan, adapter=adapter, oob_registry=None)

    def test_block_not_found_is_key_error_subclass(self, kida_env: Environment) -> None:
        """Existing ``except KeyError`` handlers must still catch it."""
        adapter = KidaAdapter(kida_env)
        plan = _plan_with_region_update(
            ViewRef(
                template="oob_layout/_layout.html",
                block="missing_oob",
                context={},
            ),
        )
        with pytest.raises(KeyError):
            execute_render_plan(plan, adapter=adapter, oob_registry=None)


class TestOptionalRegionSkipped:
    def test_optional_missing_block_drops_region_from_output(
        self, kida_env: Environment
    ) -> None:
        """optional=True missing block: region is absent from region_htmls (not
        emitted as an empty OOB wrapper, which would wipe existing DOM content)."""
        adapter = KidaAdapter(kida_env)
        reg = OOBRegistry()
        reg.register(
            "breadcrumbs_oob",
            OOBRegionConfig(target_id="breadcrumbs-region", optional=True),
        )

        plan = _plan_with_region_update(
            ViewRef(
                template="oob_layout/_layout.html",
                block="breadcrumbs_oob",
                context={},
            ),
            region="breadcrumbs-region",
        )
        rendered = execute_render_plan(plan, adapter=adapter, oob_registry=reg)
        # The optional region must NOT appear in region_htmls — skipped, not empty
        assert "breadcrumbs-region" not in rendered.region_htmls

    def test_optional_missing_not_in_serialized_html(self, kida_env: Environment) -> None:
        """Serialized output must not contain an empty hx-swap-oob wrapper for a
        dropped optional region."""
        adapter = KidaAdapter(kida_env)
        reg = OOBRegistry()
        reg.register(
            "breadcrumbs_oob",
            OOBRegionConfig(target_id="breadcrumbs-region", optional=True),
        )

        plan = _plan_with_region_update(
            ViewRef(
                template="oob_layout/_layout.html",
                block="breadcrumbs_oob",
                context={},
            ),
            region="breadcrumbs-region",
        )
        rendered = execute_render_plan(plan, adapter=adapter, oob_registry=reg)
        html = serialize_rendered_plan(rendered, oob_registry=reg)
        assert 'id="breadcrumbs-region"' not in html

    def test_optional_present_block_still_rendered(self, kida_env: Environment) -> None:
        """optional=True does NOT short-circuit when the block DOES exist — it must
        render as normal."""
        adapter = KidaAdapter(kida_env)
        reg = OOBRegistry()
        reg.register(
            "sidebar_oob",
            OOBRegionConfig(target_id="sidebar-oob", optional=True),
        )

        plan = _plan_with_region_update(
            ViewRef(
                template="oob_layout/_layout.html",
                block="sidebar_oob",
                context={},
            ),
            region="sidebar-oob",
        )
        rendered = execute_render_plan(plan, adapter=adapter, oob_registry=reg)
        assert "sidebar-oob" in rendered.region_htmls
        assert "sidebar" in rendered.region_htmls["sidebar-oob"]


class TestRealRenderErrorsStillPropagate:
    def test_render_error_in_existing_block_raises(self, kida_env: Environment) -> None:
        """If the block EXISTS but render_block fails (e.g. undefined filter or
        Kida bug), the exception must propagate — not be silently dropped."""
        from unittest.mock import patch

        adapter = KidaAdapter(kida_env)

        def boom(*args, **kwargs):  # noqa: ANN002
            raise RuntimeError("simulated template engine failure")

        plan = _plan_with_region_update(
            ViewRef(
                template="oob_layout/_layout.html",
                block="sidebar_oob",  # exists in the template
                context={},
            ),
            region="sidebar-oob",
        )
        with patch.object(adapter, "render_block", side_effect=boom):
            with pytest.raises(RuntimeError, match="simulated"):
                execute_render_plan(plan, adapter=adapter, oob_registry=None)


class TestOrphanOOBSeverity:
    """Sprint 2: check_oob_registry_coverage emits ERROR for non-optional
    orphans, WARNING for optional orphans."""

    def test_non_optional_orphan_emits_error(self, kida_env: Environment) -> None:
        from chirp.contracts.rules_oob_registry import check_oob_registry_coverage
        from chirp.contracts.types import Severity

        reg = OOBRegistry()
        reg.register(
            "shell_actions_oob",
            OOBRegionConfig(target_id="chirp-shell-actions"),
        )
        issues = check_oob_registry_coverage(
            reg,
            ["oob_layout/_layout.html"],
            kida_env,
        )
        matching = [i for i in issues if "shell_actions_oob" in i.message]
        assert matching, "expected an issue for shell_actions_oob"
        assert all(i.severity is Severity.ERROR for i in matching)

    def test_optional_orphan_emits_warning(self, kida_env: Environment) -> None:
        from chirp.contracts.rules_oob_registry import check_oob_registry_coverage
        from chirp.contracts.types import Severity

        reg = OOBRegistry()
        reg.register(
            "shell_actions_oob",
            OOBRegionConfig(target_id="chirp-shell-actions", optional=True),
        )
        issues = check_oob_registry_coverage(
            reg,
            ["oob_layout/_layout.html"],
            kida_env,
        )
        matching = [i for i in issues if "shell_actions_oob" in i.message]
        assert matching, "expected an issue for optional orphaned block"
        assert all(i.severity is Severity.WARNING for i in matching)

    def test_mixed_optional_and_required_orphans_distinct_severities(
        self, kida_env: Environment
    ) -> None:
        """Optional and required orphans in the same registry get different severities."""
        from chirp.contracts.rules_oob_registry import check_oob_registry_coverage
        from chirp.contracts.types import Severity

        reg = OOBRegistry()
        reg.register(
            "required_orphan_oob",
            OOBRegionConfig(target_id="required-t"),
        )
        reg.register(
            "optional_orphan_oob",
            OOBRegionConfig(target_id="optional-t", optional=True),
        )
        issues = check_oob_registry_coverage(
            reg,
            ["oob_layout/_layout.html"],
            kida_env,
        )
        by_block = {}
        for i in issues:
            for b in ("required_orphan_oob", "optional_orphan_oob"):
                if b in i.message:
                    by_block[b] = i.severity
        assert by_block["required_orphan_oob"] is Severity.ERROR
        assert by_block["optional_orphan_oob"] is Severity.WARNING
