"""Registration helpers for App setup APIs."""

import inspect
from collections.abc import Callable
from pathlib import Path
from typing import Any

from chirp.http.request import Request
from chirp.pages.types import Section

from .state import MutableAppState, PendingRoute, PendingTool


class AppRegistry:
    """Owns setup-time registration and page mount wiring."""

    __slots__ = ("_ensure_mutable", "_state")

    def __init__(self, state: MutableAppState, ensure_mutable: Callable[[], None]) -> None:
        self._state = state
        self._ensure_mutable = ensure_mutable

    def route(
        self,
        path: str,
        *,
        methods: list[str] | None,
        name: str | None,
        referenced: bool,
        template: str | None,
        inline: bool,
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            self._ensure_mutable()
            self._state.pending_routes.append(
                PendingRoute(path, func, methods, name, referenced, template, inline)
            )
            return func

        return decorator

    def provide(self, annotation: type, factory: Callable[..., Any]) -> None:
        self._ensure_mutable()
        self._state.providers[annotation] = factory

    def register_domain(self, domain: object) -> None:
        self._ensure_mutable()
        self._state.pending_domains.append(domain)

    def tool(
        self,
        name: str,
        *,
        description: str,
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            self._ensure_mutable()
            self._state.pending_tools.append(PendingTool(name, description, func))
            return func

        return decorator

    def error(
        self,
        code_or_exception: int | type[Exception],
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            self._ensure_mutable()
            self._state.error_handlers[code_or_exception] = func
            return func

        return decorator

    def add_middleware(self, middleware: Any) -> None:
        self._ensure_mutable()
        self._state.middleware_list.append(middleware)

    def add_reload_dir(self, path: str | Path) -> None:
        self._ensure_mutable()
        self._state.reload_dirs_extra.append(str(Path(path).resolve()))

    def register_section(self, section: Section) -> None:
        """Register a named section for route metadata resolution."""
        self._ensure_mutable()
        self._state.sections[section.id] = section

    def template_filter(
        self, name: str | None
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            self._ensure_mutable()
            filter_name = name or getattr(func, "__name__", "unknown")
            self._state.template_filters[filter_name] = func
            return func

        return decorator

    def template_global(
        self, name: str | None
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            self._ensure_mutable()
            global_name = name or getattr(func, "__name__", "unknown")
            self._state.template_globals[global_name] = func
            return func

        return decorator

    def on_startup(self, func: Callable[..., Any]) -> Callable[..., Any]:
        self._ensure_mutable()
        self._state.startup_hooks.append(func)
        return func

    def on_shutdown(self, func: Callable[..., Any]) -> Callable[..., Any]:
        self._ensure_mutable()
        self._state.shutdown_hooks.append(func)
        return func

    def on_worker_startup(self, func: Callable[..., Any]) -> Callable[..., Any]:
        self._ensure_mutable()
        self._state.worker_startup_hooks.append(func)
        return func

    def on_worker_shutdown(self, func: Callable[..., Any]) -> Callable[..., Any]:
        self._ensure_mutable()
        self._state.worker_shutdown_hooks.append(func)
        return func

    def mount_pages(self, pages_dir: str | None, *, lazy_pages: bool) -> None:
        self._ensure_mutable()
        resolved = pages_dir or "pages"
        if lazy_pages:
            self._state.lazy_pages_dir = resolved
            return
        self.discover_and_register_pages(resolved)

    def discover_and_register_pages(self, pages_dir: str) -> None:
        from chirp.pages.discovery import discover_pages

        page_routes = discover_pages(pages_dir)
        self._state.discovered_routes = page_routes
        for page_route in page_routes:
            self._state.page_route_paths.add(page_route.url_path)
            self._state.route_metas[page_route.url_path] = page_route.meta
            if page_route.template_name:
                self._state.route_templates[page_route.url_path] = page_route.template_name
            self._state.discovered_layout_chains.append(page_route.layout_chain)
            if page_route.template_name:
                self._state.page_leaf_templates.add(page_route.template_name)
                self._state.page_templates.add(page_route.template_name)
            for layout in page_route.layout_chain.layouts:
                self._state.page_templates.add(layout.template_name)

        for page_route in page_routes:
            self.register_page_handler(
                url_path=page_route.url_path,
                handler=page_route.handler,
                methods=list(page_route.methods),
                layout_chain=page_route.layout_chain,
                context_providers=page_route.context_providers,
                template_name=page_route.template_name,
                meta=page_route.meta,
                meta_provider=page_route.meta_provider,
                actions=page_route.actions,
                viewmodel_provider=page_route.viewmodel_provider,
                kind=page_route.kind,
            )

    def register_page_handler(
        self,
        *,
        url_path: str,
        handler: Callable[..., Any],
        methods: list[str],
        layout_chain: Any,
        context_providers: tuple[Any, ...],
        template_name: str | None = None,
        meta: Any = None,
        meta_provider: Any = None,
        actions: tuple[Any, ...] = (),
        viewmodel_provider: Any = None,
        kind: str = "page",
    ) -> None:
        from chirp._internal.invoke import invoke
        from chirp.pages.actions import dispatch_action
        from chirp.pages.context import build_cascade_context
        from chirp.pages.debug import build_route_debug_info, set_route_debug_metadata
        from chirp.pages.resolve import resolve_kwargs, upgrade_result
        from chirp.pages.sections import resolve_section_context
        from chirp.pages.shell_context import build_shell_context, resolve_meta

        _handler = handler
        _kind = kind
        _chain = layout_chain
        _providers = context_providers
        _template = template_name
        _meta = meta
        _meta_provider = meta_provider
        _actions = actions
        _viewmodel_provider = viewmodel_provider
        _sections = self._state.sections
        if template_name:
            self._state.page_leaf_templates.add(template_name)
            self._state.page_templates.add(template_name)
        _service_providers = self._state.providers

        async def page_wrapper(request: Request) -> Any:
            cascade_ctx = await build_cascade_context(
                _providers, request.path_params, _service_providers
            )
            meta_resolved = await resolve_meta(
                _meta, _meta_provider, request.path_params, _service_providers
            )
            section_ctx = resolve_section_context(meta_resolved, _sections)
            shell_ctx = build_shell_context(
                request, meta_resolved, section_ctx, cascade_ctx
            )
            route_debug = build_route_debug_info(
                route_kind=_kind,
                template_name=_template,
                meta=_meta,
                meta_provider=_meta_provider,
                context_providers=_providers,
                layout_chain=_chain,
                actions=_actions,
                viewmodel_provider=_viewmodel_provider,
                meta_resolved=meta_resolved,
                section_ctx=section_ctx,
                shell_ctx=shell_ctx,
            )
            set_route_debug_metadata(request, route_debug)
            base_ctx = {**cascade_ctx, **section_ctx, **shell_ctx}
            viewmodel_ctx = {}
            if _viewmodel_provider:
                from chirp.pages.context import _call_provider

                vm_result = _call_provider(
                    _viewmodel_provider,
                    request.path_params,
                    base_ctx,
                    _service_providers,
                )
                if inspect.isawaitable(vm_result):
                    vm_result = await vm_result
                if isinstance(vm_result, dict):
                    viewmodel_ctx = vm_result
            full_ctx = {**base_ctx, **viewmodel_ctx}

            # POST with actions: check _action form field first
            if request.method == "POST" and _actions:
                try:
                    form_data = dict(await request.form())
                except Exception:
                    form_data = {}
                action_name = form_data.get("_action")
                if action_name:
                    for act in _actions:
                        if act.name == action_name:
                            action_result = await dispatch_action(
                                act,
                                request.path_params,
                                full_ctx,
                                _service_providers,
                                form_data,
                            )
                            return upgrade_result(
                                action_result,
                                full_ctx,
                                _chain,
                                _providers,
                                request=request,
                                template_name=_template,
                            )

            kwargs = await resolve_kwargs(_handler, request, full_ctx, _service_providers)
            result = await invoke(_handler, **kwargs)
            return upgrade_result(
                result,
                full_ctx,
                _chain,
                _providers,
                request=request,
                template_name=_template,
            )

        self._state.pending_routes.append(
            PendingRoute(url_path, page_wrapper, methods, name=None, referenced=False)
        )
