"""Stress tests for OOBRegistry contract caching under concurrent access.

The OOBRegistry._contract_lock protects lazy LayoutContract building.
These tests verify the cache is consistent when many threads request
contracts simultaneously.
"""

import threading
from unittest.mock import MagicMock

from chirp.templating.oob_registry import OOBRegionConfig, OOBRegistry

from .conftest import STRESS_TIMEOUT, ThreadStressResult, run_threads_synchronized


def _make_mock_adapter(template_name: str) -> MagicMock:
    """Create a mock adapter that build_layout_contract can consume."""
    adapter = MagicMock()
    # The contract builder needs env.get_template().block_metadata()
    template_mock = MagicMock()
    template_mock.block_metadata.return_value = {}
    adapter.env.get_template.return_value = template_mock
    adapter.env.loader = None
    return adapter


class TestOOBRegistryContention:
    """Concurrent get_or_build_contract calls on the same template."""

    def test_concurrent_contract_builds_same_template(self) -> None:
        """Only one build happens; all threads get the same contract."""
        registry = OOBRegistry()
        registry.register("nav_oob", OOBRegionConfig(target_id="nav"))
        registry.freeze()

        build_count = 0
        build_lock = threading.Lock()
        n_threads = 50
        template_name = "layout.html"

        # Patch build_layout_contract to count calls
        original_build = None

        try:
            from chirp.templating.render_plan import build_layout_contract

            original_build = build_layout_contract

            def counting_build(adapter, name, oob_registry=None):
                nonlocal build_count
                with build_lock:
                    build_count += 1
                # Return a distinguishable sentinel
                return f"contract-for-{name}"

            # Monkey-patch the import used inside get_or_build_contract
            import chirp.templating.render_plan as rp_mod

            rp_mod.build_layout_contract = counting_build

            adapter = _make_mock_adapter(template_name)
            contracts: list[object] = []
            contracts_lock = threading.Lock()

            def worker(idx: int, barrier: threading.Barrier, result: ThreadStressResult) -> None:
                barrier.wait()
                try:
                    c = registry.get_or_build_contract(adapter, template_name)
                    with contracts_lock:
                        contracts.append(c)
                    result.record("ok")
                except Exception as exc:
                    result.record_error(exc)

            result = run_threads_synchronized(n_threads, worker, timeout=STRESS_TIMEOUT)

            assert not result.errors, f"Thread errors: {result.errors}"
            # Build should have been called exactly once (cache hit for rest)
            assert build_count == 1, f"Expected 1 build, got {build_count}"
            # All threads should get the same contract object
            assert all(c == contracts[0] for c in contracts)

        finally:
            if original_build is not None:
                import chirp.templating.render_plan as rp_mod

                rp_mod.build_layout_contract = original_build

    def test_concurrent_builds_different_templates(self) -> None:
        """Different templates can build in parallel without interference."""
        registry = OOBRegistry()
        registry.freeze()
        n_threads = 30

        import chirp.templating.render_plan as rp_mod

        original_build = rp_mod.build_layout_contract

        try:

            def mock_build(adapter, name, oob_registry=None):
                return f"contract-for-{name}"

            rp_mod.build_layout_contract = mock_build
            adapter = MagicMock()

            contracts: dict[str, list[object]] = {}
            contracts_lock = threading.Lock()

            def worker(idx: int, barrier: threading.Barrier, result: ThreadStressResult) -> None:
                template = f"template-{idx % 10}.html"
                barrier.wait()
                try:
                    c = registry.get_or_build_contract(adapter, template)
                    with contracts_lock:
                        contracts.setdefault(template, []).append(c)
                    result.record("ok")
                except Exception as exc:
                    result.record_error(exc)

            result = run_threads_synchronized(n_threads, worker, timeout=STRESS_TIMEOUT)
            assert not result.errors

            # Each template should have a consistent contract
            for template, cs in contracts.items():
                assert all(c == cs[0] for c in cs), f"Inconsistent contracts for {template}"

        finally:
            rp_mod.build_layout_contract = original_build
