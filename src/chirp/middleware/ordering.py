"""Stable priority ordering for user-registered middleware.

``App.add_middleware(mw, priority=...)`` records a per-entry ``priority`` parallel
to the middleware list (see ``MutableAppState.middleware_priorities``). The
resolved request pipeline must be deterministic and independent of registration
order, so the user middleware is sorted *once* at freeze (under the freeze lock,
before publication) by ``(priority, registration_order)``.

Two invariants make this safe to add to existing apps:

- **Lower priority runs outermost.** The compiled chain wraps later entries
  inside earlier ones (``handler.compile_middleware_chain`` iterates
  ``reversed(...)``), so a *smaller* priority sorts earlier and therefore wraps
  the rest — the first-registered / lowest-priority middleware sees the request
  first and the response last.
- **Default order is byte-identical to today.** ``sorted`` is stable and the
  default priority is ``0``, so an all-default stack keeps registration order
  exactly; the sort is a no-op for every app that never passes ``priority=``.

Builtin middleware (added by the compiler) is intentionally NOT sorted here — it
stays positionally pinned around the user middleware.
"""

from typing import Any


def sort_user_middleware(
    middleware_list: list[Any],
    priorities: list[int] | None,
) -> list[Any]:
    """Return *middleware_list* stably sorted by ``(priority, registration)``.

    *priorities* is the index-aligned priority list. When it is ``None`` or
    its length does not match (a defensively-handled inconsistency), the input
    order is returned unchanged so a length mismatch can never reorder or drop
    middleware silently. The input list is not mutated.
    """
    if not middleware_list:
        return list(middleware_list)
    if priorities is None or len(priorities) != len(middleware_list):
        return list(middleware_list)
    # enumerate() supplies the stable registration-order tiebreak so equal
    # priorities keep their add_middleware order.
    indexed = sorted(
        enumerate(middleware_list),
        key=lambda pair: (priorities[pair[0]], pair[0]),
    )
    return [mw for _, mw in indexed]
