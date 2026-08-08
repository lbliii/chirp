"""Milo MCP Apps registration and named-block resource rendering.

The adapter verifies caller-owned Milo commands and UI resources at Chirp's
freeze boundary, then projects frozen bindings through Chirp's existing
``Fragment`` / ``App.render`` surface on each resource read.
"""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Awaitable, Callable, Iterable, Mapping
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from chirp.errors import ConfigurationError
from chirp.templating.returns import Fragment

if TYPE_CHECKING:
    from milo import CLI

    from chirp.app import App

type MiloContext = Mapping[str, Any]
type MiloContextProvider = Callable[[], MiloContext | Awaitable[MiloContext]]

_MILO_INSTALL_ERROR = (
    "The chirp.ext.milo adapter requires Chirp's supported milo-cli>=0.4.1,<0.5 "
    "runtime dependency. "
    "Reinstall Chirp with `pip install --force-reinstall bengal-chirp` and retry."
)


@dataclass(frozen=True, slots=True)
class MiloMCPAppBinding:
    """One verified Chirp binding to caller-owned Milo MCP Apps metadata."""

    operation_id: str
    resource_uri: str
    visibility: tuple[str, ...]
    template: str
    block: str
    context_provider: MiloContextProvider


@dataclass(frozen=True, slots=True)
class _PendingMiloMCPAppBinding:
    operation_id: str
    template: str
    block: str
    context_provider: MiloContextProvider


class MiloMCPAppAdapter:
    """Setup compiler and per-read named-block projector for Milo MCP Apps."""

    __slots__ = (
        "_allowlist",
        "_app",
        "_bindings",
        "_bindings_by_id",
        "_check_not_frozen",
        "_cli",
        "_is_frozen",
        "_pending",
    )

    def __init__(
        self,
        cli: CLI,
        *,
        allowlist: tuple[str, ...],
        check_not_frozen: Callable[[], None],
        is_frozen: Callable[[], bool],
    ) -> None:
        self._cli = cli
        self._allowlist = allowlist
        self._check_not_frozen = check_not_frozen
        self._is_frozen = is_frozen
        self._pending: dict[str, _PendingMiloMCPAppBinding] = {}
        self._bindings: tuple[MiloMCPAppBinding, ...] = ()
        self._bindings_by_id: dict[str, MiloMCPAppBinding] = {}
        self._app: App | None = None

    @property
    def bindings(self) -> tuple[MiloMCPAppBinding, ...]:
        """Return the immutable snapshot published by a successful app freeze."""
        if not self._is_frozen():
            msg = (
                "Milo MCP App bindings are not available until the Chirp app is frozen. "
                "Call app.freeze(), app.check(), app.run(), or serve the first request."
            )
            raise RuntimeError(msg)
        return self._bindings

    def bind(
        self,
        operation_id: str,
        *,
        template: str,
        block: str,
        context: MiloContextProvider,
    ) -> None:
        """Declare one allowlisted Milo command's Chirp template/block identity."""
        self._check_not_frozen()
        operation_id = _required_name(operation_id, field="operation_id")
        template = _required_name(template, field="template")
        block = _required_name(block, field="block")
        if operation_id not in self._allowlist:
            msg = (
                f"Milo operation {operation_id!r} is not in this adapter's exact allowlist. "
                "Add the canonical dotted command ID to use_milo(..., allowlist=(...))."
            )
            raise ConfigurationError(msg)
        if operation_id in self._pending:
            msg = f"Milo operation {operation_id!r} already has a Chirp MCP App binding."
            raise ConfigurationError(msg)
        _require_parameterless(context, label=f"context provider for {operation_id!r}")
        self._pending[operation_id] = _PendingMiloMCPAppBinding(
            operation_id=operation_id,
            template=template,
            block=block,
            context_provider=context,
        )

    def render_resource(self, operation_id: str) -> str:
        """Render one frozen binding's named block for a Milo ``ui://`` resource read.

        Resolves the immutable freeze-time binding, invokes that binding's
        explicit parameterless application context provider for *this* read,
        and renders ``Fragment(template, block, **context)`` through
        ``App.render``.  Milo continues to own MIME/profile negotiation and
        protocol errors; the caller-owned ``@cli.ui_resource`` handler should
        delegate here.
        """
        if not self._is_frozen() or self._app is None:
            msg = (
                "Milo MCP App resource rendering requires a frozen Chirp app. "
                "Call app.freeze(), app.check(), app.run(), or serve the first request "
                "before reading ui:// resources."
            )
            raise RuntimeError(msg)
        operation_id = _required_name(operation_id, field="operation_id")
        binding = self._bindings_by_id.get(operation_id)
        if binding is None:
            known = ", ".join(self._bindings_by_id) or "(none)"
            msg = (
                f"Milo operation {operation_id!r} has no frozen Chirp MCP App binding. "
                f"Known bindings: {known}."
            )
            raise ConfigurationError(msg)

        context = _resolve_context(binding.context_provider, operation_id=operation_id)
        if not isinstance(context, Mapping):
            msg = (
                f"Context provider for Milo operation {operation_id!r} must return a mapping; "
                f"got {type(context).__name__}."
            )
            raise ConfigurationError(msg)
        try:
            context_kwargs = {str(key): value for key, value in context.items()}
        except (TypeError, ValueError) as exc:
            msg = (
                f"Context provider for Milo operation {operation_id!r} returned a mapping "
                "Chirp cannot unpack into template context."
            )
            raise ConfigurationError(msg) from exc

        html = self._app.render(Fragment(binding.template, binding.block, **context_kwargs))
        if not html.strip():
            msg = (
                f"Milo MCP App resource for {operation_id!r} rendered empty HTML from "
                f"template {binding.template!r} block {binding.block!r}. "
                "Required UI resources must produce non-empty markup."
            )
            raise ConfigurationError(msg)
        return html

    def register(self, app: App) -> None:
        """Compile the binding snapshot under Chirp's existing freeze lock."""
        command_map = dict(self._cli.walk_commands())
        resource_map = dict(self._cli.walk_ui_resources())
        allowlisted = set(self._allowlist)
        bound = set(self._pending)
        if bound != allowlisted:
            missing = sorted(allowlisted - bound)
            unexpected = sorted(bound - allowlisted)
            details: list[str] = []
            if missing:
                details.append(f"missing bindings: {', '.join(missing)}")
            if unexpected:
                details.append(f"bindings outside allowlist: {', '.join(unexpected)}")
            msg = "Milo MCP App bindings must exactly match the adapter allowlist; " + "; ".join(
                details
            )
            raise ConfigurationError(msg)

        compiled: list[MiloMCPAppBinding] = []
        for operation_id in sorted(self._allowlist):
            command = command_map.get(operation_id)
            if command is None:
                resolved = self._cli.get_command(operation_id)
                alias_hint = (
                    " The name resolves as an alias; bind its canonical dotted command ID instead."
                    if resolved is not None
                    else ""
                )
                msg = (
                    f"Milo operation {operation_id!r} is not a registered canonical dotted "
                    f"command ID.{alias_hint}"
                )
                raise ConfigurationError(msg)
            if "mcp" not in command.surfaces:
                msg = (
                    f"Milo operation {operation_id!r} is not enabled for the MCP surface. "
                    "Include 'mcp' in surfaces=... when the command is originally registered."
                )
                raise ConfigurationError(msg)
            tool_meta = getattr(command, "ui", None)
            if tool_meta is None:
                msg = (
                    f"Milo operation {operation_id!r} has no MCPAppToolMeta. Attach matching "
                    "ui=MCPAppToolMeta(...) when the command is originally registered."
                )
                raise ConfigurationError(msg)
            resource_uri = tool_meta.resource_uri
            if not resource_uri.startswith("ui://"):
                msg = (
                    f"Milo operation {operation_id!r} links to {resource_uri!r}; "
                    "MCP App resources must use a ui:// URI."
                )
                raise ConfigurationError(msg)
            resource = resource_map.get(resource_uri)
            if resource is None:
                msg = (
                    f"Milo operation {operation_id!r} links to UI resource {resource_uri!r}, "
                    "but the caller-owned CLI has no matching cli.ui_resource(...) registration."
                )
                raise ConfigurationError(msg)
            if resource.uri != resource_uri:
                msg = (
                    f"Milo UI resource identity mismatch for {operation_id!r}: tool metadata "
                    f"links {resource_uri!r}, resource declares {resource.uri!r}."
                )
                raise ConfigurationError(msg)
            _require_parameterless(
                resource.handler,
                label=f"Milo UI resource handler for {resource_uri!r}",
            )
            pending = self._pending[operation_id]
            _require_parameterless(
                pending.context_provider,
                label=f"context provider for {operation_id!r}",
            )
            compiled.append(
                MiloMCPAppBinding(
                    operation_id=operation_id,
                    resource_uri=resource_uri,
                    visibility=tuple(tool_meta.visibility),
                    template=pending.template,
                    block=pending.block,
                    context_provider=pending.context_provider,
                )
            )

        for binding in compiled:
            app.declare_template(binding.template, blocks=(binding.block,))

        # One assignment publishes a deterministic immutable read model.  The
        # caller-owned Milo CLI and its registries are never frozen or mutated.
        self._app = app
        self._bindings = tuple(compiled)
        self._bindings_by_id = {binding.operation_id: binding for binding in self._bindings}


def use_milo(
    app: App,
    cli: CLI,
    *,
    allowlist: Iterable[str],
) -> MiloMCPAppAdapter:
    """Register the lazy Chirp-to-Milo MCP Apps adapter for one application."""
    milo_cli_type = _load_milo_cli()
    if not isinstance(cli, milo_cli_type):
        msg = "use_milo() requires a milo.CLI instance owned by the caller."
        raise TypeError(msg)
    if isinstance(allowlist, str):
        msg = "use_milo(..., allowlist=...) requires an iterable of canonical dotted IDs, not str."
        raise TypeError(msg)
    normalized = tuple(_required_name(name, field="allowlist entry") for name in allowlist)
    if not normalized:
        msg = "use_milo(..., allowlist=...) requires at least one canonical dotted command ID."
        raise ConfigurationError(msg)
    if len(set(normalized)) != len(normalized):
        msg = "use_milo(..., allowlist=...) contains duplicate command IDs."
        raise ConfigurationError(msg)

    adapter = MiloMCPAppAdapter(
        cli,
        allowlist=normalized,
        check_not_frozen=app._check_not_frozen,
        is_frozen=lambda: app._runtime_state.frozen,
    )
    app.register_domain(adapter)
    return adapter


def _load_milo_cli() -> type[CLI]:
    try:
        import milo

        cli_type = milo.CLI
        tool_meta_type = milo.MCPAppToolMeta
    except (ImportError, AttributeError) as exc:
        raise ImportError(_MILO_INSTALL_ERROR) from exc
    required_methods = ("get_command", "walk_commands", "walk_ui_resources")
    if not isinstance(tool_meta_type, type) or any(
        not callable(getattr(cli_type, name, None)) for name in required_methods
    ):
        raise ImportError(_MILO_INSTALL_ERROR)
    return cli_type


def _required_name(value: str, *, field: str) -> str:
    if not isinstance(value, str):
        msg = f"Milo {field} must be a string."
        raise TypeError(msg)
    normalized = value.strip()
    if not normalized:
        msg = f"Milo {field} cannot be empty."
        raise ConfigurationError(msg)
    if normalized != value:
        msg = f"Milo {field} {value!r} has surrounding whitespace; use {normalized!r}."
        raise ConfigurationError(msg)
    return normalized


def _require_parameterless(func: Callable[..., Any], *, label: str) -> None:
    if not callable(func):
        msg = f"{label} must be callable."
        raise TypeError(msg)
    try:
        parameters = inspect.signature(func).parameters
    except (TypeError, ValueError) as exc:
        msg = f"{label} must expose an inspectable parameterless signature."
        raise ConfigurationError(msg) from exc
    if parameters:
        names = ", ".join(parameters)
        msg = f"{label} must be parameterless; found: {names}."
        raise ConfigurationError(msg)


def _resolve_context(provider: MiloContextProvider, *, operation_id: str) -> Any:
    """Invoke a sync or async parameterless context provider for one resource read."""
    try:
        if inspect.iscoroutinefunction(provider):
            return _run_awaitable(provider(), operation_id=operation_id)
        result = provider()
    except ConfigurationError:
        raise
    except Exception as exc:
        msg = (
            f"Context provider for Milo operation {operation_id!r} failed: "
            f"{type(exc).__name__}: {exc}"
        )
        raise ConfigurationError(msg) from exc
    if inspect.isawaitable(result):
        return _run_awaitable(result, operation_id=operation_id)
    return result


async def _await_result(awaitable: Awaitable[Any]) -> Any:
    return await awaitable


def _run_awaitable(awaitable: Awaitable[Any], *, operation_id: str) -> Any:
    """Resolve one awaitable from Milo's synchronous resource-handler thread.

    When an event loop is already running, resolve the provider in a per-call
    worker thread.  No global executor or shared mutable state is retained.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        try:
            return asyncio.run(_await_result(awaitable))
        except ConfigurationError:
            raise
        except Exception as exc:
            msg = (
                f"Async context provider for Milo operation {operation_id!r} failed: "
                f"{type(exc).__name__}: {exc}"
            )
            raise ConfigurationError(msg) from exc

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(asyncio.run, _await_result(awaitable))
        try:
            return future.result()
        except ConfigurationError:
            raise
        except Exception as exc:
            msg = (
                f"Async context provider for Milo operation {operation_id!r} failed: "
                f"{type(exc).__name__}: {exc}"
            )
            raise ConfigurationError(msg) from exc


__all__ = [
    "MiloContext",
    "MiloContextProvider",
    "MiloMCPAppAdapter",
    "MiloMCPAppBinding",
    "use_milo",
]
