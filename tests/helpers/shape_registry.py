"""Test isolation for the process-global ``@shape`` registry.

``@shape`` registers each Shape by name in a process-global registry
(``chirp.data.shapes._SHAPE_REGISTRY``). Re-executing a module that declares a
Shape — which every example/app loader does for isolation — builds a *new* class
object under the same name, and ``register_shape`` fails loud on that collision
(by design: a duplicate Shape name is a real bug in a single process). Harnesses
that load app modules more than once per process must therefore restore the
registry between loads, exactly as they already restore ``sys.modules`` and
``sys.path``.

This mirrors the existing module-purge isolation and touches no public API — it
snapshots and restores the private registry under its own lock.
"""

from __future__ import annotations

import contextlib
from collections.abc import Iterator

from chirp.data.shapes import _REGISTRY_LOCK, _SHAPE_REGISTRY


@contextlib.contextmanager
def isolated_shape_registry() -> Iterator[None]:
    """Snapshot the ``@shape`` registry on entry; restore it on exit.

    Wrap any block that loads (or reloads) an app/example module so the Shapes it
    registers do not leak into — or collide with — a later load in the same
    process.
    """
    with _REGISTRY_LOCK:
        snapshot = dict(_SHAPE_REGISTRY)
    try:
        yield
    finally:
        with _REGISTRY_LOCK:
            _SHAPE_REGISTRY.clear()
            _SHAPE_REGISTRY.update(snapshot)
