"""Application setup/runtime state containers."""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from kida import Environment

from chirp._internal.types import ErrorHandler, Handler
from chirp.middleware.protocol import Middleware
from chirp.routing.router import Router
from chirp.tools.events import ToolEventBus
from chirp.tools.registry import ToolRegistry

if TYPE_CHECKING:
    from chirp.data.database import Database


@dataclass(slots=True)
class PendingRoute:
    """A route waiting to be compiled."""

    path: str
    handler: Handler
    methods: list[str] | None
    name: str | None
    referenced: bool = False
    template: str | None = None


@dataclass(slots=True)
class PendingTool:
    """A tool waiting to be compiled."""

    name: str
    description: str
    handler: Callable[..., Any]


@dataclass(slots=True)
class MutableAppState:
    """Mutable setup-time state."""

    pending_routes: list[PendingRoute] = field(default_factory=list)
    pending_tools: list[PendingTool] = field(default_factory=list)
    middleware_list: list[Middleware] = field(default_factory=list)
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
    page_templates: set[str] = field(default_factory=set)
    pending_domains: list[object] = field(default_factory=list)
    providers: dict[type, Callable[..., Any]] = field(default_factory=dict)
    reload_dirs_extra: list[str] = field(default_factory=list)
    db: Database | None = None
    migrations_dir: str | None = None
    custom_kida_env: Environment | None = None
    tool_events: ToolEventBus = field(default_factory=ToolEventBus)


@dataclass(slots=True)
class RuntimeAppState:
    """Compiled runtime state populated during freeze."""

    frozen: bool = False
    contracts_ready: bool = False
    router: Router | None = None
    middleware: tuple[Callable[..., Any], ...] = ()
    kida_env: Environment | None = None
    tool_registry: ToolRegistry | None = None


@dataclass(frozen=True, slots=True)
class ContractCheckSnapshot:
    """Stable read model for contract checks."""

    router: Router
    kida_env: Environment | None
    layout_chains: list[Any]
    page_route_paths: set[str]
    page_templates: set[str]
    islands_contract_strict: bool
