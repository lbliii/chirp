"""Registration helpers for App setup APIs."""

from collections.abc import Callable
from pathlib import Path
from typing import Any

from chirp.http.request import Request

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
        for page_route in page_routes:
            self._state.page_route_paths.add(page_route.url_path)
            self._state.discovered_layout_chains.append(page_route.layout_chain)
            if page_route.template_name:
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
    ) -> None:
        from chirp._internal.invoke import invoke
        from chirp.pages.context import build_cascade_context
        from chirp.pages.resolve import resolve_kwargs, upgrade_result

        _handler = handler
        _chain = layout_chain
        _providers = context_providers
        _template = template_name
        _service_providers = self._state.providers

        async def page_wrapper(request: Request) -> Any:
            cascade_ctx = await build_cascade_context(
                _providers, request.path_params, _service_providers
            )
            kwargs = await resolve_kwargs(_handler, request, cascade_ctx, _service_providers)
            result = await invoke(_handler, **kwargs)
            return upgrade_result(
                result,
                cascade_ctx,
                _chain,
                _providers,
                request=request,
                template_name=_template,
            )

        self._state.pending_routes.append(
            PendingRoute(url_path, page_wrapper, methods, name=None, referenced=False)
        )
