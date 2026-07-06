"""``mount_app`` adapter — hoist a pre-freeze sub-app into a parent app.

Design notes live in ``docs/rfcs/005-mount-app.md``. Summary:

- Sub-app's ``pending_routes`` are path-prefixed and appended to the parent.
- Middleware, hooks, loaders, tools, and contract checks are **appended** —
  parent's entries run first, sub-app's follow.
- Template globals, filters, error handlers, providers, severity overrides,
  and freeze-param providers use **parent-wins** merge; dropped sub-app
  entries are recorded as ``MountAppSkip``s (surfaced later as INFO contract
  issues in category ``mount_app_merge``).
- Sub-app is marked *consumed* — subsequent ``sub_app.freeze()``/``run()``
  raise ``RuntimeError`` so the caller doesn't accidentally serve a
  half-mounted standalone runtime.

Deeper page-shell registries (sections, OOB, fragment targets,
layout presets, live blocks, page-discovery state) are not yet supported:
``mount_app`` raises ``ConfigurationError`` if the sub-app has populated
any of them. RFC 005 §3.3 treats these as "deep contracts" whose silent
override would break shell rendering; a future version may add explicit
collision handling.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from chirp.errors import ConfigurationError

from .state import MountAppSkip, PendingRoute

if TYPE_CHECKING:
    from .state import MutableAppState


def normalize_prefix(prefix: str) -> str:
    """Return ``"/" + prefix.strip("/")``.

    Raises ``ConfigurationError`` if the result would be ``"/"`` — mounting
    at root has no effect vs. registering the routes directly on the parent.
    """
    stripped = prefix.strip("/")
    if not stripped:
        msg = f"mount_app prefix must be a non-root path, e.g. '/admin'. Got prefix={prefix!r}."
        raise ConfigurationError(msg)
    return "/" + stripped


def prefixed_path(path: str, prefix: str) -> str:
    """Return the sub-app route's path after applying the mount prefix.

    ``prefix`` is pre-normalized to ``"/<something>"`` (see
    :func:`normalize_prefix`); ``path`` is whatever the sub-app registered
    (expected to start with ``"/"``).
    """
    if path == "/":
        return prefix
    return prefix + "/" + path.lstrip("/")


_UNSUPPORTED_FIELDS: tuple[tuple[str, str], ...] = (
    ("discovered_routes", "mount_pages-discovered routes"),
    ("page_route_paths", "mount_pages-discovered route paths"),
    ("page_leaf_templates", "mount_pages-discovered leaf templates"),
    ("page_templates", "mount_pages-discovered templates"),
    ("route_metas", "page route metadata"),
    ("route_templates", "page route template map"),
    ("route_layout_chains", "page layout chains"),
    ("swap_scope_map", "swap scope map"),
    ("discovered_layout_chains", "discovered layout chains"),
    ("page_handler_findings", "page handler findings"),
    ("layout_presets", "layout presets"),
    ("live_blocks", "live blocks"),
    ("sections", "sections"),
    ("pending_domains", "registered domains"),
)
"""``(attribute_name, human_description)`` pairs that must be empty on the sub-app.

These populate deep page/shell contracts; mount_app v1 does not support
hoisting them. Future versions may relax this — for now, collide-early.
"""


def _check_sub_app_simple(sub_state: MutableAppState) -> None:
    """Refuse sub-apps that carry state mount_app v1 can't hoist safely."""
    unsupported: list[str] = []
    for attr, desc in _UNSUPPORTED_FIELDS:
        value = getattr(sub_state, attr)
        if value:
            unsupported.append(desc)
    if sub_state.lazy_pages_dir is not None:
        unsupported.append("lazy_pages directory")
    if sub_state.db is not None or sub_state.migrations_dir is not None:
        unsupported.append("database / migrations")
    if sub_state.custom_kida_env is not None:
        unsupported.append("custom kida environment")
    sub_oob = sub_state.oob_registry
    if sub_oob is not None and sub_oob.registered_blocks:
        unsupported.append("OOB regions")
    sub_frag = sub_state.fragment_target_registry
    if sub_frag is not None and getattr(sub_frag, "_targets", None):
        unsupported.append("fragment targets")
    if unsupported:
        msg = (
            "mount_app does not yet support sub-apps that carry deep "
            "page/shell state: "
            + ", ".join(sorted(set(unsupported)))
            + ". Register those on the parent app directly, or track "
            "RFC 005 for future support."
        )
        raise ConfigurationError(msg)


def hoist(parent_state: MutableAppState, sub_state: MutableAppState, prefix: str) -> None:
    """Merge ``sub_state`` into ``parent_state`` at ``prefix``.

    Does not validate that either state is mutable / pre-freeze — the caller
    (``App.mount_app``) owns the lifecycle checks.
    """
    _check_sub_app_simple(sub_state)

    for pending in sub_state.pending_routes:
        parent_state.pending_routes.append(
            PendingRoute(
                path=prefixed_path(pending.path, prefix),
                handler=pending.handler,
                methods=pending.methods,
                name=pending.name,
                referenced=pending.referenced,
                template=pending.template,
                inline=pending.inline,
                page_source_handler=pending.page_source_handler,
            )
        )

    parent_state.pending_tools.extend(sub_state.pending_tools)
    parent_state.middleware_list.extend(sub_state.middleware_list)
    # Keep the parallel priority list index-aligned with middleware_list. A
    # sub-app built before this field always populates middleware_priorities in
    # lockstep with add_middleware, so the two lists are the same length here.
    parent_state.middleware_priorities.extend(sub_state.middleware_priorities)
    parent_state.startup_hooks.extend(sub_state.startup_hooks)
    parent_state.shutdown_hooks.extend(sub_state.shutdown_hooks)
    parent_state.worker_startup_hooks.extend(sub_state.worker_startup_hooks)
    parent_state.worker_shutdown_hooks.extend(sub_state.worker_shutdown_hooks)
    parent_state.plugin_loaders.extend(sub_state.plugin_loaders)
    parent_state.contract_checks.extend(sub_state.contract_checks)
    parent_state.template_declarations.extend(sub_state.template_declarations)

    for path in sub_state.reload_dirs_extra:
        if path not in parent_state.reload_dirs_extra:
            parent_state.reload_dirs_extra.append(path)
    parent_state.freeze_exclude.update(sub_state.freeze_exclude)

    def _setdefault_dict(
        kind: str,
        parent: dict[Any, Any],
        sub: dict[Any, Any],
    ) -> None:
        for key, value in sub.items():
            if key in parent:
                parent_state.mount_app_skips.append(MountAppSkip(kind, str(key), prefix))
            else:
                parent[key] = value

    _setdefault_dict("template_global", parent_state.template_globals, sub_state.template_globals)
    _setdefault_dict("template_filter", parent_state.template_filters, sub_state.template_filters)
    _setdefault_dict("provider", parent_state.providers, sub_state.providers)
    _setdefault_dict(
        "freeze_param_provider",
        parent_state.freeze_param_providers,
        sub_state.freeze_param_providers,
    )
    _setdefault_dict(
        "contract_check_data",
        parent_state.contract_check_data,
        sub_state.contract_check_data,
    )
    _setdefault_dict(
        "contract_severity_override",
        parent_state.contract_severity_overrides,
        sub_state.contract_severity_overrides,
    )

    for code_or_exc, handler in sub_state.error_handlers.items():
        if code_or_exc in parent_state.error_handlers:
            parent_state.mount_app_skips.append(
                MountAppSkip("error_handler", repr(code_or_exc), prefix)
            )
        else:
            parent_state.error_handlers[code_or_exc] = handler

    sub_state.consumed_by_mount_app_prefix = prefix
