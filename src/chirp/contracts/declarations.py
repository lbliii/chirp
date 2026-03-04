"""Route-level contract declaration types."""

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class FragmentContract:
    """Declares that a route returns a specific template fragment."""

    template: str
    block: str


@dataclass(frozen=True, slots=True)
class SSEContract:
    """Declares event types and optional fragments emitted by an SSE route."""

    event_types: frozenset[str] = frozenset()
    fragments: tuple[FragmentContract, ...] = ()


@dataclass(frozen=True, slots=True)
class FormContract:
    """Declares which dataclass a route binds form data to."""

    datacls: type
    template: str
    block: str | None = None


@dataclass(frozen=True, slots=True)
class RouteContract:
    """Full contract metadata for a route."""

    returns: FragmentContract | SSEContract | None = None
    form: FormContract | None = None
    description: str = ""


def contract(
    returns: FragmentContract | SSEContract | None = None,
    *,
    form: FormContract | None = None,
    description: str = "",
) -> Any:
    """Attach a RouteContract to a route handler."""

    route_contract = RouteContract(returns=returns, form=form, description=description)

    def decorator(func: Any) -> Any:
        func._chirp_contract = route_contract
        return func

    return decorator
