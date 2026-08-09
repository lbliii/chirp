"""Application setup/runtime state containers."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal

from kida import Environment

from chirp._internal.types import ErrorHandler, Handler
from chirp.contracts.types import Severity
from chirp.middleware.protocol import Middleware
from chirp.pages.types import LayoutPreset, PageHandlerFinding, RouteMeta, Section
from chirp.routing.route import Route
from chirp.routing.router import Router
from chirp.shell_actions import ShellActionsRenderer
from chirp.templating.fragment_target_registry import FragmentTargetRegistry
from chirp.templating.oob_registry import OOBRegistry
from chirp.tools.events import ToolEventBus
from chirp.tools.registry import ToolRegistry

from .hypermedia_program import HypermediaProgram, TemplateDeclaration

if TYPE_CHECKING:
    from chirp.app._signal_graph import _SignalGraph
    from chirp.app._suspense_dag import _SuspenseDeferDAG
    from chirp.app.htmx_manifest import HtmxProvisioningManifest
    from chirp.data.database import Database
    from chirp.data.schema.types import SchemaSnapshot
    from chirp.health import HealthCheck
    from chirp.live_blocks import LiveBlockSpec
    from chirp.pages.reactive.bus import ReactiveBus
    from chirp.realtime.signal_backplane import _SignalBackplaneDescriptor
    from chirp.realtime.signals import SignalRegistry
    from chirp.settings.registry import SettingsRegistry


@dataclass(slots=True)
class PendingRoute:
    """A route waiting to be compiled."""

    path: str
    handler: Handler
    methods: list[str] | None
    name: str | None
    referenced: bool = False
    template: str | None = None
    inline: bool = False
    query_media_types: tuple[str, ...] | None = None
    #: Original page handler for contract checks (async wrapper hides user source).
    page_source_handler: Callable[..., Any] | None = None


@dataclass(slots=True)
class PendingTool:
    """A tool waiting to be compiled."""

    name: str
    description: str
    handler: Callable[..., Any]
    approval_required: bool = False


@dataclass(frozen=True, slots=True)
class MountAppSkip:
    """One entry dropped during ``App.mount_app`` merge (parent-wins).

    Recorded on the parent's mutable state so a contract check can surface it
    as an INFO issue in category ``mount_app_merge`` — users see what their
    sub-app tried to register but was overridden.
    """

    kind: str
    """One of ``"template_global"``, ``"template_filter"``, ``"error_handler"``,
    ``"provider"``, ``"contract_severity_override"``, ``"freeze_param_provider"``."""

    key: str
    prefix: str


@dataclass(frozen=True, slots=True)
class PluginQuarantine:
    """One plugin whose ``register()`` raised during ``App.mount``.

    Mounting wraps the lone ``plugin.register(app, prefix)`` call so a single
    broken plugin is *quarantined* (skipped) instead of aborting boot. The
    quarantine is recorded on the app's mutable state and surfaced as an ERROR
    issue in category ``plugin_quarantine`` by a contract check — mirroring the
    ``MountAppSkip`` -> ``mount_app_merge`` precedent. A non-fatal WARNING is
    also logged at ``mount`` time so the signal exists even when contract checks
    are skipped (honors root AGENTS.md "no silent except").

    Partial registration is a known limitation: a plugin that registers some
    routes before raising leaves that partial state behind; quarantine does not
    roll it back (full transactional mount is out of scope).
    """

    prefix: str
    plugin_repr: str
    error: str


@dataclass(frozen=True, slots=True)
class InternalRouteSpec:
    """Framework-owned URL surface published at freeze time."""

    path: str
    owner: str
    kind: Literal["asset", "api", "page", "sse", "dispatcher"]
    transport: Literal["javascript", "json", "html", "sse"]
    enabled: bool = True
    visibility: Literal["hidden", "internal", "user"] = "internal"
    reserved_prefix: str | None = None

    def owns(self, path: str) -> bool:
        """Return whether this spec reserves *path*."""
        prefix = self.reserved_prefix
        if prefix is not None:
            return path == prefix or path.startswith(prefix + "/")
        return path == self.path


@dataclass(frozen=True, slots=True)
class DebugInjectionSpec:
    """One debug runtime browser bootstrap resource."""

    name: str
    snippet: str
    asset_path: str | None = None
    before: str = "</body>"
    full_page_only: bool = False
    skip_htmx: bool = True


@dataclass(frozen=True, slots=True)
class InternalFeatureSpec:
    """A native internal/debug feature and the routes/resources it owns."""

    name: str
    enabled: bool
    reason: str
    route_paths: tuple[str, ...] = ()
    injections: tuple[DebugInjectionSpec, ...] = ()


@dataclass(frozen=True, slots=True)
class RuntimeDebugWiring:
    """Frozen debug/internal wiring descriptor published with runtime state."""

    routes: tuple[InternalRouteSpec, ...] = ()
    features: tuple[InternalFeatureSpec, ...] = ()
    trace_store: Any = None

    def internal_route_for_path(self, path: str) -> InternalRouteSpec | None:
        """Return the internal route spec that owns *path*, if any."""
        for spec in self.routes:
            if spec.owns(path):
                return spec
        return None


@dataclass(slots=True)
class MutableAppState:
    """Mutable setup-time state."""

    pending_routes: list[PendingRoute] = field(default_factory=list)
    pending_tools: list[PendingTool] = field(default_factory=list)
    middleware_list: list[Middleware] = field(default_factory=list)
    #: Per-entry priority for ``middleware_list``, kept index-aligned with it
    #: (one int per registered USER middleware). Lower runs *outermost* (wraps
    #: later ones); default ``0``. The freeze-time sort uses ``(priority,
    #: insertion_seq)`` so equal priorities preserve registration order and a
    #: stack with all-default priorities resolves byte-identically to today's
    #: append order. Builtin middleware (added in the compiler) is NOT recorded
    #: here — it stays positionally pinned. ``mount_app`` extends both lists in
    #: lockstep so a hoisted sub-app keeps its priorities.
    middleware_priorities: list[int] = field(default_factory=list)
    error_handlers: dict[int | type, ErrorHandler] = field(default_factory=dict)
    template_filters: dict[str, Callable[..., Any]] = field(default_factory=dict)
    template_globals: dict[str, Any] = field(default_factory=dict)
    startup_hooks: list[Callable[..., Any]] = field(default_factory=list)
    shutdown_hooks: list[Callable[..., Any]] = field(default_factory=list)
    worker_startup_hooks: list[Callable[..., Any]] = field(default_factory=list)
    worker_shutdown_hooks: list[Callable[..., Any]] = field(default_factory=list)
    discovered_layout_chains: list[Any] = field(default_factory=list)
    lazy_pages_dir: str | None = None
    page_route_paths: set[str] = field(default_factory=set)
    page_leaf_templates: set[str] = field(default_factory=set)
    page_templates: set[str] = field(default_factory=set)
    template_declarations: list[TemplateDeclaration] = field(default_factory=list)
    pending_domains: list[object] = field(default_factory=list)
    providers: dict[type, Callable[..., Any]] = field(default_factory=dict)
    reload_dirs_extra: list[str] = field(default_factory=list)
    db: Database | None = None
    migrations_dir: str | None = None
    custom_kida_env: Environment | None = None
    tool_events: ToolEventBus = field(default_factory=ToolEventBus)
    oob_registry: OOBRegistry = field(default_factory=OOBRegistry)
    fragment_target_registry: FragmentTargetRegistry = field(default_factory=FragmentTargetRegistry)
    sections: dict[str, Section] = field(default_factory=dict)
    #: Declared permission names (``app.register_permission``). When non-empty,
    #: the ``auth_spec`` contract check is registry-backed: an ``AuthSpec`` /
    #: bare-string permission not in this set is a startup ERROR (env-aware).
    permission_registry: set[str] = field(default_factory=set)
    #: Named policy callables (``app.register_policy``). The shared auth core
    #: resolves an ``AuthSpec.policy`` NAME against this mapping at request time;
    #: the ``auth_spec`` check flags a named policy missing from it at startup.
    policy_registry: dict[str, Callable[..., Any]] = field(default_factory=dict)
    #: Declared machine-token scope names (``app.register_scope``). The
    #: machine-auth counterpart to ``permission_registry``: when non-empty the
    #: ``auth_spec`` check ERRORs (env-aware) on any ``AuthSpec.scopes`` entry not
    #: in this set. Scopes are the token axis (webhook/cron/provisioning),
    #: deliberately separate from human permissions.
    scope_registry: set[str] = field(default_factory=set)
    route_metas: dict[str, RouteMeta | None] = field(default_factory=dict)
    route_templates: dict[str, str] = field(default_factory=dict)
    discovered_routes: list[Any] = field(default_factory=list)
    page_handler_findings: list[PageHandlerFinding] = field(default_factory=list)
    route_layout_chains: dict[str, Any] = field(default_factory=dict)
    swap_scope_map: dict[str, str] = field(default_factory=dict)
    layout_presets: dict[str, LayoutPreset] = field(default_factory=dict)
    plugin_loaders: list[Any] = field(default_factory=list)
    contract_checks: list[Callable[..., Any]] = field(default_factory=list)
    contract_check_data: dict[str, Any] = field(default_factory=dict)
    contract_severity_overrides: dict[str, Severity] = field(default_factory=dict)
    freeze_param_providers: dict[str, Callable[..., Any]] = field(default_factory=dict)
    freeze_exclude: set[str] = field(default_factory=set)
    live_blocks: dict[tuple[str, str], LiveBlockSpec] = field(default_factory=dict)
    #: Registry of ``@app.signal`` / ``@app.derived`` declarations. Holds the
    #: signal + derived spec maps, the SSR value cache, and the fan-out bus.
    #: Lazily created on first ``@app.signal``/``@app.derived`` so apps with no
    #: signals never construct a ``ReactiveBus``.
    signal_registry: SignalRegistry | None = None
    #: Runtime-mutable operator settings (``app.register_setting``). Lazily
    #: created on first registration; persisted via an optional store wired at
    #: ``App()`` construction.
    settings_registry: SettingsRegistry | None = None
    #: Optional JSON file path for :class:`~chirp.settings.store.FileSettingsStore`.
    #: When omitted and a database is wired, settings persist in ``_chirp_settings``.
    settings_store_path: str | None = None
    #: App-owned :class:`~chirp.pages.reactive.bus.ReactiveBus` instances
    #: (``app.register_reactive_bus``). ``kick_user`` closes matching subscribers
    #: on every registered bus plus the signal registry bus when present.
    reactive_buses: list[ReactiveBus] = field(default_factory=list)
    mount_app_skips: list[MountAppSkip] = field(default_factory=list)
    #: Plugins quarantined during ``App.mount`` because their ``register()``
    #: raised. Appended only during single-threaded setup (``mount`` is
    #: ``_check_not_frozen``-guarded), then copied into the frozen snapshot —
    #: same publication boundary as ``mount_app_skips``, no new lock needed. A
    #: contract check surfaces each as an ERROR in category ``plugin_quarantine``.
    plugin_quarantines: list[PluginQuarantine] = field(default_factory=list)
    #: Set when this app has been consumed by another app's ``mount_app``.
    #: Subsequent ``freeze()``/``run()`` raise rather than produce a stale
    #: standalone runtime. Carries the prefix for the error message.
    consumed_by_mount_app_prefix: str | None = None
    #: Readiness checks for the auto-mounted ``/ready`` probe
    #: (``app.add_health_check``). Before-freeze registration; a
    #: ``Database.probe()``-backed check is auto-appended at freeze when a db is
    #: wired. The per-request ``/ready`` read iterates this list directly.
    health_checks: list[HealthCheck] = field(default_factory=list)
    #: Explicit shell-actions HTML renderer (template/block). Transport
    #: (OOB target/wrap) stays fixed; ``use_chirp_ui`` sets the chirp-ui
    #: adapter. Default ``None`` means the UI-neutral Chirp renderer.
    shell_actions_renderer: ShellActionsRenderer | None = None
    #: Startup-complete gate for the ``/ready`` probe. This is a
    #: lifecycle-bounded flag, NOT a freeze violation: it has a single writer
    #: (``LifecycleCoordinator._on_startup`` sets it ``True`` after all startup
    #: hooks run; ``_on_shutdown`` resets it), is monotonic within a process
    #: life, and is never late-registered. The request handler reads this bool
    #: lock-free — acceptable for a monotonic flag set once at startup. See
    #: ``app/AGENTS.md`` "Setup then freeze" — this is setup-then-runtime
    #: mutation crossing the lifecycle boundary by design.
    ready: bool = False


@dataclass(slots=True)
class RuntimeAppState:
    """Compiled runtime state populated during freeze."""

    frozen: bool = False
    contracts_ready: bool = False
    router: Router | None = None
    middleware: tuple[Callable[..., Any], ...] = ()
    kida_env: Environment | None = None
    tool_registry: ToolRegistry | None = None
    oob_registry: OOBRegistry | None = None
    fragment_target_registry: FragmentTargetRegistry | None = None
    shell_actions_renderer: ShellActionsRenderer | None = None
    discovered_routes: list[Any] = field(default_factory=list)
    route_layout_chains: dict[str, Any] = field(default_factory=dict)
    swap_scope_map: dict[str, str] = field(default_factory=dict)
    routes_by_name: Any = None
    route_name_collisions: dict[str, list[Route]] = field(default_factory=dict)
    debug_wiring: RuntimeDebugWiring = field(default_factory=RuntimeDebugWiring)
    hypermedia_program: HypermediaProgram | None = None
    #: Private immutable producer/dependency/sink topology compiled at freeze.
    _signal_graph: _SignalGraph | None = None
    #: Private Suspense defer execution DAG (keys/blocks/edges) compiled at freeze.
    _suspense_defer_dag: _SuspenseDeferDAG | None = None
    htmx_manifest: HtmxProvisioningManifest | None = None
    #: Internal frozen signal transport selection; not a public inspection API.
    _signal_backplane_descriptor: _SignalBackplaneDescriptor | None = None


@dataclass(frozen=True, slots=True)
class ContractCheckSnapshot:
    """Stable read model for contract checks.

    Third-party contract checks receive this snapshot alongside a
    ``CheckResult`` to append issues to.  The ``template_sources`` dict
    contains ``{template_name: source_text}`` for every loaded template,
    and ``extras`` carries arbitrary data registered via
    ``app.set_contract_check_data()``.
    """

    router: Router
    kida_env: Environment | None
    layout_chains: list[Any]
    page_route_paths: set[str]
    page_leaf_templates: set[str]
    page_templates: set[str]
    fragment_target_registry: FragmentTargetRegistry
    islands_contract_strict: bool
    oob_registry: OOBRegistry | None = None
    sections: dict[str, Section] = field(default_factory=dict)
    #: Declared permission names (``app.register_permission``); empty when no
    #: registry was declared. The ``auth_spec`` check is registry-backed when
    #: non-empty (unknown permission -> ERROR) and heuristic-only otherwise.
    permission_registry: frozenset[str] = field(default_factory=frozenset)
    #: Declared policy NAMES (``app.register_policy``); empty when none declared.
    #: The ``auth_spec`` check flags an ``AuthSpec.policy`` name absent from it.
    policy_registry: frozenset[str] = field(default_factory=frozenset)
    #: Declared machine-token scope names (``app.register_scope``); empty when
    #: none declared. When non-empty the ``auth_spec`` check ERRORs (env-aware)
    #: on an ``AuthSpec.scopes`` entry absent from it (registry-backed like
    #: permissions; the machine-auth axis).
    scope_registry: frozenset[str] = field(default_factory=frozenset)
    route_metas: dict[str, RouteMeta | None] = field(default_factory=dict)
    route_templates: dict[str, str] = field(default_factory=dict)
    discovered_routes: list[Any] = field(default_factory=list)
    page_handler_findings: list[PageHandlerFinding] = field(default_factory=list)
    route_name_collisions: dict[str, list[Route]] = field(default_factory=dict)
    mount_app_skips: list[MountAppSkip] = field(default_factory=list)
    #: Plugins quarantined during ``App.mount`` (``register()`` raised). The
    #: ``plugin_quarantine`` check emits one ERROR per entry.
    plugin_quarantines: list[PluginQuarantine] = field(default_factory=list)
    debug_wiring: RuntimeDebugWiring = field(default_factory=RuntimeDebugWiring)
    template_sources: dict[str, str] = field(default_factory=dict)
    extras: dict[str, Any] = field(default_factory=dict)
    #: Names of every registered ``@app.signal`` / ``@app.derived`` producer.
    #: The signal dead-binding check validates ``sse-swap`` listeners against
    #: this explicit producer set (AST inference is insufficient — signal names
    #: are dynamic by nature). Empty when no signals are registered.
    signal_names: frozenset[str] = field(default_factory=frozenset)
    #: Declared runtime settings specs for the ``settings_spec`` contract check.
    settings_specs: tuple[Any, ...] = ()
    #: Declared database schema parsed from migrations (or live-introspected),
    #: or ``None`` for HTML-only / db-less apps. Source for the ``data`` shape
    #: contract; keeps the typed-SQL column-mapping check no-op without a db.
    schema: SchemaSnapshot | None = None
    #: Internal compiled application model. Not a public inspection API.
    _hypermedia_program: HypermediaProgram | None = None
    #: Internal immutable signal topology. Not exposed to custom check behavior yet.
    _signal_graph: _SignalGraph | None = None
    #: Internal Suspense defer execution DAG for #949 independence checks.
    _suspense_defer_dag: _SuspenseDeferDAG | None = None
    #: Internal frozen htmx provisioning decision. Not a public inspection API.
    _htmx_manifest: HtmxProvisioningManifest | None = None
    #: Internal frozen signal transport selection; not exposed to custom checks.
    _signal_backplane_descriptor: _SignalBackplaneDescriptor | None = None
