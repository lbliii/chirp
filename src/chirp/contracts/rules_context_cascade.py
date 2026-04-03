"""Context cascade contract validation.

Inspects ``_context.py`` provider chains for each page route and reports:

- **Shadowing**: A child provider contributes a key already contributed by a parent.
- **Unresolvable params**: A provider parameter cannot be satisfied by path params,
  parent context, or registered service providers.
"""

import inspect
import re
from typing import Any

from .types import ContractIssue, Severity


def check_context_cascade(
    discovered_routes: list[Any],
    providers: dict[type, Any] | None,
) -> list[ContractIssue]:
    """Validate context provider chains for cascade correctness."""
    issues: list[ContractIssue] = []
    provider_types = set(providers.keys()) if providers else set()
    # Names that the cascade system injects automatically
    builtin_names = {"request", "context", "cascade_ctx"}

    for route in discovered_routes:
        context_providers = getattr(route, "context_providers", ())
        if len(context_providers) < 2:
            continue

        url_path = getattr(route, "url_path", "")
        path_params: set[str] = set()
        if "{" in url_path:
            for m in re.finditer(r"\{(\w+)\}", url_path):
                path_params.add(m.group(1))

        # Track which keys each depth contributes
        contributed_keys: dict[str, int] = {}  # key -> depth that first contributed it
        available_keys: set[str] = set(path_params) | builtin_names

        for provider in context_providers:
            func = getattr(provider, "func", None)
            depth = getattr(provider, "depth", 0)
            module_path = getattr(provider, "module_path", "?")
            if func is None:
                continue

            # Check that this provider's params are resolvable
            try:
                sig = inspect.signature(func, eval_str=True)
            except Exception:
                continue

            for name, param in sig.parameters.items():
                if name in builtin_names:
                    continue
                if name in path_params:
                    continue
                if name in available_keys:
                    continue
                if (
                    param.annotation is not inspect.Parameter.empty
                    and param.annotation in provider_types
                ):
                    continue
                if param.default is not inspect.Parameter.empty:
                    continue
                issues.append(
                    ContractIssue(
                        severity=Severity.WARNING,
                        category="context_cascade",
                        message=(
                            f"Route '{url_path}' context provider at depth {depth} "
                            f"({module_path}) requires param '{name}' which is not "
                            "available from path params, parent context, or service providers."
                        ),
                        route=url_path,
                    )
                )

            # Estimate contributed keys from the function's return annotation or name
            # Since we can't run the function, we inspect what the function *might*
            # contribute by looking at dict literal returns in source (best-effort).
            try:
                source = inspect.getsource(func)
                # Look for return {"key": ...} or return dict(key=...)
                contributed = _extract_return_keys(source)
            except TypeError, OSError:
                contributed = set()

            for key in contributed:
                if key in contributed_keys:
                    prior_depth = contributed_keys[key]
                    if prior_depth < depth:
                        issues.append(
                            ContractIssue(
                                severity=Severity.INFO,
                                category="context_cascade",
                                message=(
                                    f"Route '{url_path}' context key '{key}' is provided "
                                    f"at depth {prior_depth} and overridden at depth {depth} "
                                    f"({module_path}). Child overrides parent."
                                ),
                                route=url_path,
                            )
                        )
                contributed_keys[key] = depth
                available_keys.add(key)

    return issues


def _extract_return_keys(source: str) -> set[str]:
    """Best-effort extraction of dict keys from return statements.

    Handles common patterns:
    - return {"key": value, ...}
    - return dict(key=value, ...)
    """
    keys: set[str] = set()
    # Match return {"key": ...} patterns
    for m in re.finditer(r"return\s*\{([^}]+)\}", source):
        body = m.group(1)
        for km in re.finditer(r'["\'](\w+)["\']', body):
            keys.add(km.group(1))
    # Match return dict(key=...) patterns
    for m in re.finditer(r"return\s+dict\(([^)]+)\)", source):
        body = m.group(1)
        for km in re.finditer(r"(\w+)\s*=", body):
            keys.add(km.group(1))
    return keys
