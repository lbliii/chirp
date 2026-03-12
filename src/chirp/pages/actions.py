"""Action discovery and dispatch for _actions.py.

Discovers @action decorated functions and dispatches by _action form field.
"""

from __future__ import annotations

import inspect
from typing import Any

from chirp.pages.types import ActionInfo


def action(name: str) -> Any:
    """Decorator to register a named action in _actions.py.

    The action name is used as the value for the _action form field.
    """

    def decorator(func: Any) -> Any:
        func._chirp_action_name = name
        return func

    return decorator


def load_actions(actions_module: Any) -> tuple[ActionInfo, ...]:
    """Load ActionInfo from a module with @action decorated functions."""
    result: list[ActionInfo] = []
    for attr_name in dir(actions_module):
        if attr_name.startswith("_"):
            continue
        obj = getattr(actions_module, attr_name)
        if not callable(obj):
            continue
        action_name = getattr(obj, "_chirp_action_name", None)
        if action_name is None:
            continue
        result.append(ActionInfo(name=action_name, func=obj))
    return tuple(result)


async def dispatch_action(
    action_info: ActionInfo,
    path_params: dict[str, str],
    cascade_ctx: dict[str, Any],
    service_providers: dict[type, Any],
    form_data: dict[str, Any] | None = None,
) -> Any:
    """Invoke an action with path params, context, and services.

    Resolves handler kwargs same as context providers. Returns the
    action's return value (may be Redirect, Fragment, OOB, etc.).
    """
    form_data = form_data or {}
    kwargs = _resolve_action_kwargs(
        action_info.func, path_params, cascade_ctx, service_providers, form_data
    )
    result = action_info.func(**kwargs)
    if inspect.isawaitable(result):
        return await result
    return result


def _resolve_action_kwargs(
    func: Any,
    path_params: dict[str, str],
    cascade_ctx: dict[str, Any],
    service_providers: dict[type, Any],
    form_data: dict[str, Any],
) -> dict[str, Any]:
    """Resolve kwargs for action function (same pattern as _call_provider)."""
    sig = inspect.signature(func, eval_str=True)
    kwargs: dict[str, Any] = {}

    for name, param in sig.parameters.items():
        if name in path_params:
            value = path_params[name]
            if param.annotation is not inspect.Parameter.empty:
                try:
                    kwargs[name] = param.annotation(value)
                except ValueError, TypeError:
                    kwargs[name] = value
            else:
                kwargs[name] = value
        elif name in cascade_ctx:
            kwargs[name] = cascade_ctx[name]
        elif name in form_data:
            kwargs[name] = form_data[name]
        elif (
            param.annotation is not inspect.Parameter.empty
            and param.annotation in service_providers
        ):
            kwargs[name] = service_providers[param.annotation]()

    return kwargs
