"""Tests for ``chirp.security.resolve_permissions`` — group -> permission rollup.

The helper is a pure function the app calls inside its own ``load_user`` to turn
a user's group memberships into the flat ``user.permissions`` frozenset that
``chirp.security.auth_core.enforce_auth`` checks. These tests pin:

- the OR-merge contract (most-permissive-wins = set UNION, never intersection);
- truthy-leaf dotted flatten (falsy leaves grant nothing);
- both accepted blob shapes (``Iterable[str]`` and nested ``Mapping``);
- ``base`` merge, immutability, and order-independence; and
- the @pytest.mark.issue(374) acceptance test: a resolved set fed through the
  real ``enforce_auth`` gate grants/denies via the existing exact match.
"""

from dataclasses import dataclass

import anyio
import pytest

from chirp.middleware.auth import (
    UserWithPermissions,
    _active_config,
    _user_var,
)
from chirp.pages.types import AuthSpec
from chirp.security import resolve_permissions
from chirp.security.auth_core import enforce_auth

# ---------------------------------------------------------------------------
# Core helper
# ---------------------------------------------------------------------------


class TestResolvePermissions:
    def test_empty_input_returns_base(self) -> None:
        assert resolve_permissions([]) == frozenset()
        base = frozenset({"a", "b"})
        assert resolve_permissions([], base=base) == base

    def test_single_flat_blob_passes_through(self) -> None:
        result = resolve_permissions([{"billing.read", "billing.write"}])
        assert result == frozenset({"billing.read", "billing.write"})

    def test_two_overlapping_blobs_union_not_intersection(self) -> None:
        # GUARDRAIL: most-permissive-wins is a UNION. An intersection would
        # silently strip permissions and under-grant.
        result = resolve_permissions([{"a", "b"}, {"b", "c"}])
        assert result == frozenset({"a", "b", "c"})

    def test_nested_mapping_truthy_leaves_only(self) -> None:
        result = resolve_permissions([{"billing": {"read": True, "write": False}}])
        assert result == frozenset({"billing.read"})
        # A falsy leaf must never emit its dotted key.
        assert "billing.write" not in result

    def test_nested_mapping_deep(self) -> None:
        result = resolve_permissions([{"a": {"b": {"c": True, "d": False}, "e": True}}])
        assert result == frozenset({"a.b.c", "a.e"})

    def test_mixed_blob_shapes(self) -> None:
        result = resolve_permissions(
            [
                {"reports.view"},  # flat Iterable[str]
                {"billing": {"read": True}},  # nested Mapping
            ]
        )
        assert result == frozenset({"reports.view", "billing.read"})

    def test_base_merges_in(self) -> None:
        result = resolve_permissions([{"billing.read"}], base=frozenset({"profile.edit"}))
        assert result == frozenset({"billing.read", "profile.edit"})

    def test_string_blob_is_single_permission(self) -> None:
        # A bare str is iterable char-by-char; it must be treated as ONE name.
        result = resolve_permissions(["admin"])
        assert result == frozenset({"admin"})

    def test_returns_frozenset(self) -> None:
        result = resolve_permissions([{"a"}])
        assert isinstance(result, frozenset)

    def test_order_independent(self) -> None:
        a = resolve_permissions([{"a", "b"}, {"c"}])
        b = resolve_permissions([{"c"}, {"b", "a"}])
        assert a == b

    def test_idempotent_on_same_input(self) -> None:
        blobs = [{"billing": {"read": True}}, {"reports.view"}]
        assert resolve_permissions(blobs) == resolve_permissions(blobs)


# ---------------------------------------------------------------------------
# Acceptance: the resolved set feeds the REAL gate (exact match)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class GroupUser:
    """BYO user shape: id + is_authenticated + flat permissions frozenset."""

    id: str
    permissions: frozenset[str]
    is_authenticated: bool = True


class _FakeRequest:
    """Minimal request: API-style (Authorization header) to force the 401 path."""

    def __init__(self) -> None:
        self.path = "/x"
        self.method = "GET"
        self.url = "/x"
        self.headers = {"authorization": "Bearer t"}


def _enforce(user: GroupUser, spec: AuthSpec) -> None:
    """Run enforce_auth with the user ContextVar set (no full request)."""

    async def runner() -> None:
        tok = _user_var.set(user)
        cfg_tok = _active_config.set(None)
        try:
            await enforce_auth(spec, _FakeRequest(), user)
        finally:
            _user_var.reset(tok)
            _active_config.reset(cfg_tok)

    anyio.run(runner)


@pytest.mark.issue(374)
def test_resolved_permissions_feed_the_real_gate() -> None:
    """resolve_permissions output lands on user.permissions and the existing
    exact-match gate (auth_core.py:206-213) grants/denies correctly.

    Proves the helper is wired into the real authorization path — not just a set
    function in isolation.
    """
    from chirp.errors import HTTPError

    # App computes the flat set from group blobs (as it would in load_user).
    perms = resolve_permissions(
        [
            {"billing": {"read": True, "write": False}},  # nested -> billing.read
            {"reports.view"},  # flat passthrough
        ],
        base=frozenset({"profile.edit"}),
    )
    user = GroupUser(id="u", permissions=perms)

    # Sanity: the result is exactly the union of truthy leaves + base.
    assert user.permissions == frozenset({"billing.read", "reports.view", "profile.edit"})
    # The user satisfies the permissions protocol the gate requires.
    assert isinstance(user, UserWithPermissions)

    # GRANT: mode="all" subset is satisfied by the resolved set.
    _enforce(user, AuthSpec(permissions=("billing.read", "reports.view"), mode="all"))

    # GRANT: mode="any" intersection is non-empty.
    _enforce(user, AuthSpec(permissions=("billing.read", "admin"), mode="any"))

    # DENY: a permission the user lacks (falsy leaf dropped -> no billing.write).
    with pytest.raises(HTTPError) as exc:
        _enforce(user, AuthSpec(permissions=("billing.write",), mode="all"))
    assert exc.value.status == 403

    # DENY: exact match means a held "billing.read" does NOT cover required
    # "billing" (no dotted-prefix coverage in the core helper path).
    with pytest.raises(HTTPError) as exc:
        _enforce(user, AuthSpec(permissions=("billing",), mode="all"))
    assert exc.value.status == 403
