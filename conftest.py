"""Repo-root pytest hooks.

Capability-lane skip-fail (#917) must load for specialized jobs under
``examples/`` as well as ``tests/``. A root conftest is visible to every
invocation whose rootdir is the repository; ``tests/conftest.py`` alone is
not a parent of ``examples/``.

The plugin is inert unless ``CHIRP_CAPABILITY_LANE`` is set.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Early conftest loading can omit the repo root on sys.path (importlib mode /
# plugin preparse). Ensure ``tests.capability`` imports resolve.
_REPO_ROOT = Path(__file__).resolve().parent
_root = str(_REPO_ROOT)
if _root not in sys.path:
    sys.path.insert(0, _root)

pytest_plugins = ["tests.capability.plugin"]
