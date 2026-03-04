"""Diagnostics and contract checking for App."""

from chirp.config import AppConfig
from chirp.server.terminal_checks import format_check_result


class ContractCheckRunner:
    """Runs contract checks and formats terminal output."""

    __slots__ = ("_config",)

    def __init__(self, config: AppConfig) -> None:
        self._config = config

    def run_debug_checks(self, app: object) -> None:
        import sys

        from chirp.contracts import check_hypermedia_surface

        result = check_hypermedia_surface(app)
        sys.stderr.write(format_check_result(result))
        if not result.ok:
            sys.exit(1)

    def check(self, app: object) -> None:
        from chirp.contracts import check_hypermedia_surface

        result = check_hypermedia_surface(app)
        print(format_check_result(result, color=None))
        if not result.ok:
            raise SystemExit(1)
