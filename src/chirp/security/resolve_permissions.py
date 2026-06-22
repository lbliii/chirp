"""Group -> permission rollup helper.

Chirp's authorization gate (:func:`chirp.security.auth_core.enforce_auth`)
resolves against a **flat** ``user.permissions`` frozenset and assumes something
upstream already flattened the user's group memberships into that set. This
module ships the flattener: a pure-stdlib :func:`resolve_permissions` that the
app calls inside its own ``load_user`` so the result lands on ``user.permissions``
and feeds the existing exact-match gate unchanged.

It is a primitive the app wires by hand — there is no DB-backed Group/User model
here. Persistence stays the app's choice; this honors the BYO-user Protocol and
the no-ORM stance.

Usage inside ``load_user``::

    from chirp.security import resolve_permissions

    def load_user(user_id: str) -> User | None:
        record = db.get_user(user_id)
        if record is None:
            return None
        perms = resolve_permissions(
            [group.permissions for group in record.groups],
            base=frozenset(record.direct_permissions),
        )
        return User(id=record.id, permissions=perms)

Each group blob may be either:

- an ``Iterable[str]`` of already-flat permission names
  (e.g. ``{"billing.read", "billing.write"}``), passed straight through, or
- a nested truthy-leaf ``Mapping`` (e.g. ``{"billing": {"read": True,
  "write": False}}``) flattened to dotted keys — only **truthy** leaves are
  emitted, so the example yields ``{"billing.read"}`` and never
  ``"billing.write"``.

Groups are OR-merged (most-permissive-wins = set **union**, never intersection):
a permission held by *any* group is held by the user. The result includes
``base`` and is always a ``frozenset`` (immutable, thread-safe by construction).
"""

from collections.abc import Iterable, Mapping
from typing import Any

__all__ = ["resolve_permissions"]


def _flatten_mapping(mapping: Mapping[Any, Any], prefix: str) -> set[str]:
    """Recursively flatten a nested mapping to dotted, truthy-leaf keys.

    Keys are joined with ``"."`` (stringified); only truthy leaves are emitted,
    so a ``{"read": False}`` leaf grants nothing. ``prefix`` carries the
    accumulated dotted path during recursion.
    """
    out: set[str] = set()
    for key, value in mapping.items():
        dotted = f"{prefix}.{key}" if prefix else f"{key}"
        if isinstance(value, Mapping):
            out |= _flatten_mapping(value, dotted)
        elif value:  # truthy leaf only — a falsy leaf grants nothing
            out.add(dotted)
    return out


def _flatten_blob(blob: Mapping[str, Any] | Iterable[str]) -> set[str]:
    """Flatten one group blob into a set of dotted permission strings.

    A ``Mapping`` is walked recursively (truthy-leaf dotted flatten). Any other
    iterable of strings is taken as already-flat permission names. A bare ``str``
    is itself iterable but is a single permission, not a sequence of one-char
    names, so it is handled directly.
    """
    if isinstance(blob, Mapping):
        return _flatten_mapping(blob, "")
    if isinstance(blob, str):
        return {blob}
    return set(blob)


def resolve_permissions(
    group_blobs: Iterable[Mapping[str, Any] | Iterable[str]],
    *,
    base: frozenset[str] = frozenset(),
) -> frozenset[str]:
    """OR-merge group permission blobs into a flat ``frozenset[str]``.

    The most-permissive-wins rollup an app's ``load_user`` runs to turn a user's
    group memberships into the flat ``user.permissions`` set that
    :func:`chirp.security.auth_core.enforce_auth` checks.

    Args:
        group_blobs: One blob per group the user belongs to. Each blob is either
            an ``Iterable[str]`` of already-flat permission names, or a nested
            truthy-leaf ``Mapping`` (e.g. ``{"billing": {"read": True}}``)
            flattened to dotted keys (``"billing.read"``). Only truthy leaves are
            emitted; a ``{"read": False}`` leaf grants nothing.
        base: Permissions granted regardless of group membership (e.g. a user's
            direct grants). Merged into the result via union.

    Returns:
        The union of ``base`` and every group's flattened permissions, as a
        ``frozenset``. Empty input returns ``base`` unchanged (as a frozenset).
        The result is immutable and the function holds no shared state, so it is
        thread-safe by construction.

    Note:
        Merging is strict set **union** (OR-merge): a permission held by *any*
        group is held by the user. It is never an intersection — that would
        silently strip permissions and under-grant. Matching of the resulting
        set against required permissions stays **exact** in the gate; this helper
        does not implement dotted-prefix coverage (a held ``"billing"`` does not
        cover a required ``"billing.read"``).
    """
    merged: set[str] = set(base)
    for blob in group_blobs:
        merged |= _flatten_blob(blob)
    return frozenset(merged)
