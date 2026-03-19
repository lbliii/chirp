"""Compilation pipeline from mutable setup state to runtime state."""

from collections.abc import Callable
from pathlib import Path
from typing import Any

from chirp._internal.invoke_plan import compile_invoke_plan
from chirp.config import AppConfig
from chirp.routing.route import Route
from chirp.routing.router import Router, parse_path
from chirp.templating.integration import create_environment
from chirp.tools.registry import compile_tools

from .registry import AppRegistry
from .state import MutableAppState, RuntimeAppState


def _collect_builtin_middleware(
    config: AppConfig,
    middleware_list: list,
) -> list:
    """Append builtin middleware (static, safe_target, sse_lifecycle, etc.) to list."""
    if config.static_dir is not None:
        static_path = Path(config.static_dir).resolve()
        if static_path.is_dir():
            from chirp.middleware.static import StaticFiles

            prefix = config.static_url.strip("/") or "static"
            middleware_list.append(StaticFiles(directory=str(static_path), prefix=f"/{prefix}"))
    if config.safe_target:
        from chirp.middleware.inject import HTMLInject
        from chirp.server.htmx_safe_target import SAFE_TARGET_SNIPPET

        middleware_list.append(HTMLInject(SAFE_TARGET_SNIPPET, full_page_only=True))
    if config.sse_lifecycle:
        from chirp.middleware.inject import HTMLInject
        from chirp.server.sse_lifecycle import SSE_LIFECYCLE_SNIPPET

        middleware_list.append(HTMLInject(SSE_LIFECYCLE_SNIPPET, full_page_only=True))
    if config.delegation:
        from chirp.middleware.inject import HTMLInject
        from chirp.server.delegation import DELEGATION_SNIPPET

        middleware_list.append(HTMLInject(DELEGATION_SNIPPET, full_page_only=True))
    if config.alpine:
        from chirp.middleware.inject import HTMLInject
        from chirp.server.alpine import alpine_snippet

        middleware_list.append(
            HTMLInject(
                alpine_snippet(config.alpine_version, config.alpine_csp),
                full_page_only=True,
            )
        )
    if config.islands:
        from chirp.middleware.inject import HTMLInject
        from chirp.server.islands import islands_snippet

        middleware_list.append(
            HTMLInject(islands_snippet(config.islands_version), full_page_only=True)
        )
    if config.view_transitions:
        from chirp.middleware.inject import HTMLInject
        from chirp.server.view_transitions import (
            VIEW_TRANSITIONS_HEAD_SNIPPET,
            VIEW_TRANSITIONS_SCRIPT_SNIPPET,
        )

        middleware_list.append(
            HTMLInject(
                VIEW_TRANSITIONS_HEAD_SNIPPET,
                before="</head>",
                full_page_only=True,
            )
        )
        middleware_list.append(HTMLInject(VIEW_TRANSITIONS_SCRIPT_SNIPPET, full_page_only=True))
    if config.debug:
        from chirp.middleware.inject import HTMLInject
        from chirp.middleware.layout_debug import LayoutDebugMiddleware
        from chirp.server.htmx_debug import HTMX_DEBUG_BOOT_SNIPPET

        middleware_list.append(LayoutDebugMiddleware())
        middleware_list.append(HTMLInject(HTMX_DEBUG_BOOT_SNIPPET))
    return middleware_list


def _compile_routes(
    pending_routes: list,
    providers: dict[type, Callable[..., Any]],
) -> Router:
    """Build router from pending routes."""
    router = Router()
    for pending in pending_routes:
        methods = frozenset(m.upper() for m in (pending.methods or ["GET"]))
        segments = parse_path(pending.path)
        path_param_names = frozenset(s.param_name for s in segments if s.is_param and s.param_name)
        invoke_plan = compile_invoke_plan(
            pending.handler,
            providers,
            path_param_names=path_param_names,
            inline=pending.inline,
        )
        route = Route(
            path=pending.path,
            handler=pending.handler,
            methods=methods,
            name=pending.name,
            referenced=pending.referenced,
            template=pending.template,
            invoke_plan=invoke_plan,
            inline=pending.inline,
        )
        router.add(route)
    router.compile()
    return router


class AppCompiler:
    """Compiles app setup state into immutable runtime state."""

    __slots__ = ("_config", "_mutable", "_registry", "_runtime")

    def __init__(
        self,
        config: AppConfig,
        registry: AppRegistry,
        mutable_state: MutableAppState,
        runtime_state: RuntimeAppState,
    ) -> None:
        self._config = config
        self._registry = registry
        self._mutable = mutable_state
        self._runtime = runtime_state

    def freeze(
        self,
        app: object,
        run_debug_checks: Callable[[], None],
        sync_runtime_aliases: Callable[[], None],
    ) -> None:
        self._runtime.contracts_ready = False
        for domain in self._mutable.pending_domains:
            register = getattr(domain, "register", None)
            if register is not None and callable(register):
                register(app)

        if self._mutable.lazy_pages_dir is not None:
            self._registry.discover_and_register_pages(self._mutable.lazy_pages_dir)
            self._mutable.lazy_pages_dir = None

        router = _compile_routes(
            self._mutable.pending_routes,
            self._mutable.providers,
        )
        self._runtime.router = router
        self._runtime.discovered_routes = list(self._mutable.discovered_routes)

        middleware_list = list(self._mutable.middleware_list)
        middleware_list = _collect_builtin_middleware(self._config, middleware_list)
        self._runtime.middleware = tuple(middleware_list)

        for middleware in self._runtime.middleware:
            mw_globals = getattr(middleware, "template_globals", None)
            if mw_globals and isinstance(mw_globals, dict):
                for name, func in mw_globals.items():
                    self._mutable.template_globals.setdefault(name, func)

        if self._mutable.custom_kida_env is not None:
            self._runtime.kida_env = self._mutable.custom_kida_env
            if self._mutable.template_filters:
                self._runtime.kida_env.update_filters(self._mutable.template_filters)
            for name, value in self._mutable.template_globals.items():
                self._runtime.kida_env.add_global(name, value)
        else:
            self._runtime.kida_env = create_environment(
                self._config,
                self._mutable.template_filters,
                self._mutable.template_globals,
            )

        self._runtime.tool_registry = compile_tools(
            [(t.name, t.description, t.handler) for t in self._mutable.pending_tools],
            self._mutable.tool_events,
        )
        from chirp.shell_actions import SHELL_ACTIONS_TARGET
        from chirp.templating.oob_registry import OOBRegionConfig

        if self._mutable.oob_registry.get("shell_actions_oob") is None:
            self._mutable.oob_registry.register(
                "shell_actions_oob",
                OOBRegionConfig(target_id=SHELL_ACTIONS_TARGET, swap="innerHTML", wrap=True),
            )
        self._mutable.oob_registry.freeze()
        self._runtime.oob_registry = self._mutable.oob_registry

        self._mutable.fragment_target_registry.freeze()
        self._runtime.fragment_target_registry = self._mutable.fragment_target_registry

        self._runtime.frozen = True

        sync_runtime_aliases()
        if self._config.debug and not self._config.skip_contract_checks:
            run_debug_checks()
