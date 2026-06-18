"""Compilation pipeline from mutable setup state to runtime state."""

from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from chirp._internal.invoke_plan import compile_invoke_plan
from chirp.config import AppConfig
from chirp.routing.route import Route
from chirp.routing.router import Router, parse_path
from chirp.templating.integration import create_environment
from chirp.templating.oob_registry import OOBRegistry
from chirp.tools.registry import compile_tools

from .registry import AppRegistry
from .state import MutableAppState, RuntimeAppState, RuntimeDebugWiring

if TYPE_CHECKING:
    from chirp.app import App


def _collect_builtin_middleware(
    config: AppConfig,
    middleware_list: list,
    *,
    router: object | None = None,
    oob_registry: OOBRegistry | None = None,
    debug_wiring: RuntimeDebugWiring | None = None,
) -> list:
    """Append builtin middleware (static, safe_target, sse_lifecycle, etc.) to list."""
    # AllowedHostsMiddleware — reject bad hosts first
    from chirp.middleware.allowed_hosts import AllowedHostsMiddleware

    middleware_list.insert(0, AllowedHostsMiddleware(config.allowed_hosts, debug=config.debug))

    # CacheMiddleware — site-wide GET caching (opt-in)
    if config.cache_middleware_enabled:
        from chirp.cache import create_backend
        from chirp.cache.middleware import CacheMiddleware

        backend = create_backend(config.cache_backend)
        middleware_list.append(CacheMiddleware(backend, ttl=config.cache_default_ttl))

    # LocaleMiddleware — i18n locale detection
    if config.i18n_enabled:
        from chirp.i18n.middleware import LocaleMiddleware

        middleware_list.append(
            LocaleMiddleware(
                supported_locales=config.i18n_supported_locales,
                default_locale=config.i18n_default_locale,
                cookie_name=config.i18n_cookie_name,
                url_prefix=config.i18n_url_prefix,
            )
        )

    # CSP nonce middleware
    if config.csp_nonce_enabled:
        from chirp.middleware.csp_nonce import CSPNonceMiddleware

        # Alpine needs 'unsafe-eval' (expressions are eval'd) AND style-src
        # 'unsafe-inline' (x-show writes un-nonceable inline style attrs). Both
        # are scoped narrowly: script-src stays nonce-only + 'unsafe-eval', and
        # the inline relaxation is confined to style-src. The @alpinejs/csp build
        # (alpine_csp) needs neither.
        needs_eval = config.alpine and not config.alpine_csp
        middleware_list.append(
            CSPNonceMiddleware(unsafe_eval=needs_eval, style_unsafe_inline=needs_eval)
        )

    # HSTS auto-enable in production with TLS
    if config.env == "production" and config.ssl_certfile and not config.strict_transport_security:
        # Auto-set HSTS — mutating config is not possible (frozen),
        # so we add SecurityHeadersMiddleware with HSTS manually
        from chirp.middleware.security_headers import (
            SecurityHeadersConfig,
            SecurityHeadersMiddleware,
        )

        needs_eval = config.alpine and not config.alpine_csp
        eval_directive = " 'unsafe-eval'" if needs_eval else ""
        csp = (
            "default-src 'self'; "
            f"script-src 'self'{eval_directive}"
            " https://unpkg.com https://cdn.jsdelivr.net; "
            "base-uri 'self'; frame-ancestors 'none'; object-src 'none'"
        )
        sec_config = SecurityHeadersConfig(
            strict_transport_security="max-age=63072000; includeSubDomains",
            content_security_policy=csp,
        )
        middleware_list.append(SecurityHeadersMiddleware(sec_config))

    if config.static_dir is not None:
        static_path = Path(config.static_dir).resolve()
        if static_path.is_dir():
            from chirp.middleware.static import StaticFiles

            prefix = config.static_url.strip("/") or "static"
            cache = "no-cache" if config.debug else "public, max-age=3600"
            middleware_list.append(
                StaticFiles(
                    directory=str(static_path),
                    prefix=f"/{prefix}",
                    cache_control=cache,
                    stream_threshold=config.static_stream_threshold,
                )
            )
    # Every framework inline-script injection below is registered with a
    # per-request snippet *factory* (``nonce -> snippet``) rather than a fixed
    # string, so each ``<script>`` carries the live CSP nonce when a nonce
    # mechanism is active (CSPNonceMiddleware / csp_nonce_enabled) and survives a
    # strict nonce-only CSP. ``HTMLInject`` resolves the factory in request scope
    # from ``csp_nonce()`` (empty string when nonces are off). The per-request
    # cost is one string format. View-transitions HEAD markup is a
    # ``<meta>``/``<style>`` pair governed by ``style-src`` (not ``script-src``),
    # so it stays un-nonced.
    if config.safe_target:
        from chirp.middleware.inject import HTMLInject
        from chirp.server.htmx_safe_target import safe_target_snippet

        middleware_list.append(
            HTMLInject(lambda nonce: safe_target_snippet(nonce), full_page_only=True)
        )
    if config.sse_lifecycle:
        from chirp.middleware.inject import HTMLInject
        from chirp.server.sse_lifecycle import sse_lifecycle_snippet

        middleware_list.append(
            HTMLInject(lambda nonce: sse_lifecycle_snippet(nonce), full_page_only=True)
        )
    if config.delegation:
        from chirp.middleware.inject import HTMLInject
        from chirp.server.delegation import delegation_snippet

        middleware_list.append(
            HTMLInject(lambda nonce: delegation_snippet(nonce), full_page_only=True)
        )
    if config.alpine:
        from chirp.middleware.inject import AlpineInject
        from chirp.server.alpine import alpine_snippet

        # The inline ``safeData`` bootstrap is nonced; the external plugin/core
        # ``src=`` tags are unchanged. This lets a standard ``alpine=True`` app
        # run under a strict nonce-only CSP without adopting ``alpine_csp=True``.
        alpine_version = config.alpine_version
        alpine_csp = config.alpine_csp
        middleware_list.append(
            AlpineInject(
                lambda nonce: alpine_snippet(alpine_version, alpine_csp, nonce=nonce),
                full_page_only=True,
            )
        )
    if config.htmx:
        from chirp.middleware.inject import StreamingHTMLInject
        from chirp.server.htmx import htmx_snippet

        # Mirror the Alpine path: dedup on ``data-chirp="htmx"`` so a template
        # that already ships its own htmx <script> (chirp-ui shell/boost, the v2
        # scaffold) is left untouched, and rewrite StreamingResponse chunks
        # (Suspense shells) via the same async_stream_inject_before_body path.
        # The external htmx core tag carries the live per-request nonce so it
        # survives a strict nonce-only CSP. ``StreamingHTMLInject`` already
        # implements both the buffered and streaming branches plus dedup, so no
        # bespoke injection subclass is needed.
        htmx_version = config.htmx_version
        middleware_list.append(
            StreamingHTMLInject(
                lambda nonce: htmx_snippet(htmx_version, nonce=nonce),
                full_page_only=True,
                dedup_marker='data-chirp="htmx"',
            )
        )
    if config.islands:
        from chirp.middleware.inject import HTMLInject
        from chirp.server.islands import islands_snippet

        islands_version = config.islands_version
        middleware_list.append(
            HTMLInject(
                lambda nonce: islands_snippet(islands_version, nonce=nonce),
                full_page_only=True,
            )
        )
    from chirp.server.view_transitions import normalize_view_transitions

    vt_mode = normalize_view_transitions(config.view_transitions)
    if vt_mode in ("htmx", "full"):
        from chirp.middleware.inject import HTMLInject
        from chirp.server.view_transitions import view_transitions_script_snippet

        middleware_list.append(
            HTMLInject(lambda nonce: view_transitions_script_snippet(nonce), full_page_only=True)
        )
    if vt_mode == "full":
        from chirp.middleware.inject import HTMLInject
        from chirp.server.view_transitions import VIEW_TRANSITIONS_HEAD_SNIPPET

        # HEAD markup is a <meta>/<style> pair governed by style-src, not
        # script-src — left un-nonced by design.
        middleware_list.append(
            HTMLInject(
                VIEW_TRANSITIONS_HEAD_SNIPPET,
                before="</head>",
                full_page_only=True,
            )
        )
    if config.speculation_rules and router is not None:
        from chirp.server.speculation_rules import (
            build_speculation_rules_json,
            normalize_speculation_rules,
        )

        sr_mode = normalize_speculation_rules(config.speculation_rules)
        if sr_mode != "off":
            # Compute the rules JSON once at freeze time (it depends only on the
            # router); the factory only varies the nonce attribute per request.
            # A <script type="speculationrules"> element is governed by
            # script-src, so it must carry the live nonce under a nonce-only CSP.
            rules_json = build_speculation_rules_json(router, sr_mode)
            if rules_json:
                from chirp.middleware.inject import HTMLInject

                safe_json = rules_json.replace("<", "\\u003c").replace("&", "\\u0026")

                def _speculation_snippet(nonce: str, _json: str = safe_json) -> str:
                    nonce_attr = f' nonce="{nonce}"' if nonce else ""
                    return (
                        f'<script type="speculationrules" '
                        f'data-chirp="speculation-rules"{nonce_attr}>{_json}</script>'
                    )

                middleware_list.append(
                    HTMLInject(_speculation_snippet, before="</head>", full_page_only=True)
                )
    if config.debug:
        from chirp.middleware.inject import HTMLInject
        from chirp.middleware.layout_debug import LayoutDebugMiddleware

        middleware_list.append(LayoutDebugMiddleware())
        if debug_wiring is not None:
            for feature in debug_wiring.features:
                if not feature.enabled:
                    continue
                middleware_list.extend(
                    [
                        HTMLInject(
                            injection.snippet,
                            before=injection.before,
                            full_page_only=injection.full_page_only,
                            skip_htmx=injection.skip_htmx,
                        )
                        for injection in feature.injections
                    ]
                )
        if vt_mode == "off":
            from chirp.middleware.inject import ViewTransitionCssDebugWarning

            middleware_list.append(ViewTransitionCssDebugWarning())
        if config.debug_fragment_validator and oob_registry is not None:
            from chirp.middleware.debug_fragment_validator import DebugFragmentValidator

            middleware_list.append(DebugFragmentValidator(oob_registry))
    return middleware_list


def _compile_routes(
    pending_routes: list,
    providers: dict[type, Callable[..., Any]] | None,
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
            page_source_handler=pending.page_source_handler,
        )
        router.add(route)
    router.compile()
    return router


def _reject_reserved_prefix_collisions(pending_routes: list, prefix: str) -> None:
    """Raise if any pending route starts with a framework-reserved URL prefix.

    The block-fetch dispatcher owns ``/_frag/**`` — a user route like
    ``/_frag/custom`` would either shadow the dispatcher or be shadowed by it,
    and there's no policy where that ambiguity is a good idea. Fail fast with
    a message that points the user at what to change.
    """
    bad = [r for r in pending_routes if r.path == prefix or r.path.startswith(prefix + "/")]
    if not bad:
        return
    from chirp.errors import ConfigurationError

    lines = "\n".join(f"  - {r.path}" for r in bad)
    raise ConfigurationError(
        f"Route path cannot start with reserved prefix {prefix!r}; "
        "this prefix is owned by the block-fetch dispatcher. "
        f"Rename the following route(s):\n{lines}"
    )


def _reject_internal_route_collisions(
    pending_routes: list,
    debug_wiring: RuntimeDebugWiring,
) -> None:
    """Raise if a user route collides with Chirp-owned internal URL space."""
    collisions: list[tuple[str, str, str]] = []
    for route in pending_routes:
        path = getattr(route, "path", "")
        for spec in debug_wiring.routes:
            if spec.owns(path):
                reserved = spec.reserved_prefix or spec.path
                collisions.append((path, spec.owner, reserved))
                break
    if not collisions:
        return
    from chirp.errors import ConfigurationError

    lines = "\n".join(
        f"  - {path} (reserved by {owner}, namespace {reserved!r})"
        for path, owner, reserved in collisions
    )
    raise ConfigurationError(
        "Route path collides with Chirp's reserved internal runtime URL space "
        "(reserved prefix). "
        "Rename the following route(s):\n"
        f"{lines}"
    )


def _resolve_session_cookie_secure(middleware_list: list, env: str) -> None:
    """Resolve ``SessionConfig.secure`` (``"auto"`` -> bool) at freeze, by env.

    ``secure`` defaults to the string ``"auto"``, which means "Secure in
    production/staging, off in local dev". The store reads ``cfg.secure`` and
    passes it straight to ``with_cookie`` (typed ``bool``), so the string must
    be resolved to a concrete bool before any request runs. Doing it at freeze
    keeps resolution deterministic and statically checkable, and uses
    ``config.env`` — the single posture signal — exactly like the secret_key
    env gate and the security-stack severity matrix.

    Detection is by class **name** (``type(mw).__name__``), mirroring the
    contracts layer, so a SessionMiddleware is found without importing it here
    purely for an isinstance check. The actual resolution is delegated to the
    middleware's ``resolve_secure``, which also resolves the store's inner
    config (the two-config pattern).
    """
    for mw in middleware_list:
        if type(mw).__name__ == "SessionMiddleware":
            resolve = getattr(mw, "resolve_secure", None)
            if callable(resolve):
                resolve(env)


def _validate_middleware_ordering(middleware_list: list) -> None:
    """Check that middleware dependencies are satisfied.

    CSRFMiddleware requires SessionMiddleware to wrap it (i.e. Session must
    be registered *before* CSRF in add_middleware calls).  Detects the
    mis-ordering early at freeze time rather than waiting for a request to
    fail.
    """
    from chirp.middleware.csrf import CSRFMiddleware
    from chirp.middleware.sessions import SessionMiddleware

    seen_session = False
    for mw in middleware_list:
        if isinstance(mw, SessionMiddleware):
            seen_session = True
        elif isinstance(mw, CSRFMiddleware) and not seen_session:
            from chirp.errors import ConfigurationError

            msg = (
                "CSRFMiddleware requires SessionMiddleware. "
                "Add SessionMiddleware before CSRFMiddleware:\n\n"
                "    app.add_middleware(SessionMiddleware(SessionConfig(secret_key=...)))\n"
                "    app.add_middleware(CSRFMiddleware(CSRFConfig()))\n"
            )
            raise ConfigurationError(msg)


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

        # Auto-include a Database.probe()-backed readiness check when a db is
        # wired, so the auto-mounted /ready probe reflects DB connectivity with
        # no hand-wiring. Idempotent: never append twice across re-freeze.
        # Guarded by hasattr so a duck-typed db without probe() (test stubs,
        # legacy facades) does not break freeze — only a real Database opts in.
        db = self._mutable.db
        probe = getattr(db, "probe", None)
        if (
            db is not None
            and callable(probe)
            and not any(hc.name == "database" for hc in self._mutable.health_checks)
        ):
            from chirp.health import HealthCheck

            self._mutable.health_checks.append(
                HealthCheck("database", check=probe, message="database: probe failed")
            )

        from chirp.server.debug_runtime import build_runtime_debug_wiring

        debug_wiring = build_runtime_debug_wiring(self._config)
        self._runtime.debug_wiring = debug_wiring
        _reject_internal_route_collisions(self._mutable.pending_routes, debug_wiring)

        if self._config.debug and self._config.dev_browser_reload:
            from chirp.server.dev_browser_reload import (
                is_dev_browser_reload_enabled,
                make_dev_reload_pending_route,
            )

            if is_dev_browser_reload_enabled(self._config):
                self._mutable.pending_routes.append(make_dev_reload_pending_route(self._config))

        from chirp.server.fragment_dispatch import (
            FRAGMENT_ROUTE_PREFIX,
            make_fragment_dispatch_pending_route,
        )

        _reject_reserved_prefix_collisions(self._mutable.pending_routes, FRAGMENT_ROUTE_PREFIX)
        self._mutable.pending_routes.append(make_fragment_dispatch_pending_route(cast("App", app)))

        # Signals: auto-register the single merged /_chirp/live stream IFF any
        # signal exists, mirroring the live_blocks gating. Apps with no signals
        # pay nothing — no route, no globals, no ReactiveBus.
        signal_registry = self._mutable.signal_registry
        if signal_registry is not None and not signal_registry.empty:
            from chirp.realtime.signal_globals import (
                SIGNAL_STREAM_PREFIX,
                make_signal_globals,
            )
            from chirp.realtime.signal_stream import make_signal_pending_route

            _reject_reserved_prefix_collisions(self._mutable.pending_routes, SIGNAL_STREAM_PREFIX)
            self._mutable.pending_routes.append(make_signal_pending_route(signal_registry))
            for name, fn in make_signal_globals(signal_registry).items():
                self._mutable.template_globals.setdefault(name, fn)

        router = _compile_routes(
            self._mutable.pending_routes,
            self._mutable.providers,
        )
        self._runtime.router = router
        self._runtime.discovered_routes = list(self._mutable.discovered_routes)

        from chirp.app.url_for import build_routes_by_name

        routes_by_name, name_collisions = build_routes_by_name(router.routes)
        self._runtime.routes_by_name = routes_by_name
        self._runtime.route_name_collisions = name_collisions

        middleware_list = list(self._mutable.middleware_list)
        _validate_middleware_ordering(middleware_list)
        middleware_list = _collect_builtin_middleware(
            self._config,
            middleware_list,
            router=router,
            oob_registry=self._mutable.oob_registry,
            debug_wiring=debug_wiring,
        )
        # Resolve SessionConfig.secure="auto" -> concrete bool using config.env
        # (production/staging -> Secure cookies, local dev -> off). Must run
        # before publication so no request ever sees the "auto" sentinel.
        _resolve_session_cookie_secure(middleware_list, self._config.env)
        self._runtime.middleware = tuple(middleware_list)

        for middleware in self._runtime.middleware:
            mw_globals = getattr(middleware, "template_globals", None)
            if mw_globals and isinstance(mw_globals, dict):
                for name, func in mw_globals.items():
                    existing = self._mutable.template_globals.get(name)
                    if (
                        existing is None
                        or getattr(existing, "__name__", None) == "_chirpui_empty_csrf_token"
                    ):
                        self._mutable.template_globals[name] = func

        # Register i18n template global if enabled
        if self._config.i18n_enabled:
            from chirp.i18n import init_catalog, t

            init_catalog(str(self._config.i18n_directory))
            self._mutable.template_globals.setdefault("t", t)

        if self._config.alpine:
            from chirp.server.alpine import alpine_json_config

            self._mutable.template_globals.setdefault("alpine_json_config", alpine_json_config)

        from chirp.server.fragment_dispatch import fragment_url as _fragment_url

        self._mutable.template_globals.setdefault("fragment_url", _fragment_url)

        def _request_aware_url_for(name: str, /, **params: Any) -> str:
            app_ref = cast("App", app)
            try:
                from chirp.context import get_request

                request = get_request()
            except LookupError:
                return app_ref.url_for(name, **params)
            try:
                return request.url_for(name, **params)
            except RuntimeError:
                return app_ref.url_for(name, **params)

        self._mutable.template_globals.setdefault("url_for", _request_aware_url_for)

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
                plugin_loaders=self._mutable.plugin_loaders,
            )

        self._runtime.route_layout_chains = dict(self._mutable.route_layout_chains)
        self._runtime.swap_scope_map = dict(self._mutable.swap_scope_map)
        if (
            "swap_attrs" not in self._mutable.template_globals
            and self._runtime.kida_env is not None
        ):
            from chirp.templating.navigation_swap import make_swap_attrs

            self._runtime.kida_env.add_global(
                "swap_attrs",
                make_swap_attrs(
                    route_layout_chains=self._runtime.route_layout_chains,
                    router=self._runtime.router,
                    fragment_target_registry=self._mutable.fragment_target_registry,
                    swap_scope_map=self._runtime.swap_scope_map,
                ),
            )

        # Wire kida's {% trans %} blocks to chirp's i18n catalog
        if self._config.i18n_enabled and self._runtime.kida_env is not None:
            from chirp.i18n import get_catalog as _get_catalog
            from chirp.i18n import get_locale

            def _gettext(message: str) -> str:
                catalog = _get_catalog()
                if catalog is None:
                    return message
                return catalog.translate(get_locale(), message)

            def _ngettext(singular: str, plural: str, n: int) -> str:
                # Plural selection only — chirp's JSON catalogs don't store
                # plural form rules, so we pick singular/plural by English
                # rules (n==1) and return untranslated.  Full ngettext with
                # CLDR plural categories requires a catalog format upgrade.
                return singular if n == 1 else plural

            cast(Any, self._runtime.kida_env).install_gettext_callables(_gettext, _ngettext)

        self._runtime.tool_registry = compile_tools(
            [(t.name, t.description, t.handler) for t in self._mutable.pending_tools],
            self._mutable.tool_events,
        )
        from chirp.shell_actions import SHELL_ACTIONS_TARGET
        from chirp.templating.oob_registry import OOBRegionConfig

        if self._mutable.oob_registry.get("shell_actions_oob") is None:
            # Auto-registered: layouts without an explicit shell_actions region
            # are common (narrow apps, marketing pages), so mark optional so
            # the contract check doesn't block freeze for them.
            self._mutable.oob_registry.register(
                "shell_actions_oob",
                OOBRegionConfig(
                    target_id=SHELL_ACTIONS_TARGET,
                    swap="innerHTML",
                    wrap=True,
                    optional=True,
                ),
            )
        self._mutable.oob_registry.freeze()
        self._runtime.oob_registry = self._mutable.oob_registry

        self._mutable.fragment_target_registry.freeze()
        self._runtime.fragment_target_registry = self._mutable.fragment_target_registry

        self._runtime.frozen = True

        sync_runtime_aliases()
        if self._config.debug and not self._config.skip_contract_checks:
            run_debug_checks()
