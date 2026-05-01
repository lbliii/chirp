"""Diagnostics and contract checking for App."""

import time
from typing import TYPE_CHECKING

from chirp.config import AppConfig
from chirp.server.terminal_checks import format_check_result
from chirp.templating.fragment_target_registry import FragmentTargetRegistry

if TYPE_CHECKING:
    from chirp.app import App


class ContractCheckRunner:
    """Runs contract checks and formats terminal output."""

    __slots__ = ("_config",)

    def __init__(self, config: AppConfig) -> None:
        self._config = config

    def _registry(self, app: App) -> FragmentTargetRegistry | None:
        state = getattr(app, "_mutable_state", None)
        if state is None:
            return None
        registry = getattr(state, "fragment_target_registry", None)
        return registry if isinstance(registry, FragmentTargetRegistry) else None

    def run_debug_checks(self, app: App) -> None:
        import sys

        from chirp.contracts import check_hypermedia_surface

        started = time.perf_counter()
        result = check_hypermedia_surface(app)
        result.elapsed_ms = (time.perf_counter() - started) * 1000
        sys.stderr.write(
            format_check_result(
                result,
                fragment_target_registry=self._registry(app),
                verbose_registry=self._config.debug,
            )
        )
        if not result.ok:
            sys.exit(1)

    def check(
        self,
        app: App,
        *,
        warnings_as_errors: bool = False,
        coverage: bool = False,
    ) -> None:
        from chirp.contracts import check_hypermedia_surface

        started = time.perf_counter()
        result = check_hypermedia_surface(app)
        result.elapsed_ms = (time.perf_counter() - started) * 1000
        print(
            format_check_result(
                result,
                color=None,
                fragment_target_registry=self._registry(app),
                verbose_registry=self._config.debug,
                show_coverage=coverage,
            )
        )
        has_warnings = len(result.warnings) > 0
        if not result.ok or (warnings_as_errors and has_warnings):
            raise SystemExit(1)
