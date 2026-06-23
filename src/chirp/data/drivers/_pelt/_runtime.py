"""Free-threading runtime probes for pelt (epic E6).

Centralizes the ``Py_GIL_DISABLED`` / ``sys._is_gil_enabled()`` checks so tests,
CI gates, and the row-decode hot path share one definition of "GIL actually off".
"""

from __future__ import annotations

import sys
import sysconfig

# Parallel decode only pays off once row materialization dominates codec work.
_MIN_ROWS_FOR_PARALLEL = 64
_MIN_CELLS_FOR_PARALLEL = 256


def is_free_threading_build() -> bool:
    """True when the interpreter was built with ``Py_GIL_DISABLED`` support."""
    return bool(sysconfig.get_config_var("Py_GIL_DISABLED"))


def is_free_threading_enabled() -> bool:
    """True on a free-threaded build with the GIL actually disabled at runtime."""
    if not is_free_threading_build():
        return False
    return sys._is_gil_enabled() is False


def should_parallelize(*, n_rows: int, n_cols: int) -> bool:
    """Whether row decode should fan out across worker threads."""
    if n_rows < _MIN_ROWS_FOR_PARALLEL or n_cols < 1:
        return False
    if n_rows * n_cols < _MIN_CELLS_FOR_PARALLEL:
        return False
    return is_free_threading_enabled()
