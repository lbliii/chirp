"""Project scaffolding templates for ``chirp new``.

Re-exports all template constants from submodules.
"""

from chirp.cli.templates.full import (
    APP_PY,
    BASE_HTML,
    INDEX_HTML,
    STYLE_CSS,
    TEST_APP_PY,
)
from chirp.cli.templates.minimal import (
    MINIMAL_APP_PY,
    MINIMAL_INDEX_HTML,
)
from chirp.cli.templates.shell import (
    SHELL_APP_PY,
    SHELL_CONTEXT_PY,
    SHELL_ITEMS_LAYOUT_HTML,
    SHELL_ITEMS_PAGE_HTML,
    SHELL_ITEMS_PAGE_PY,
    SHELL_LAYOUT_CHIRPUI_HTML,
    SHELL_LAYOUT_HTML,
    SHELL_PAGE_HTML,
    SHELL_PAGE_PY,
)
from chirp.cli.templates.sse import (
    SSE_APP_PY,
    SSE_INDEX_HTML,
)
from chirp.cli.templates.v2 import (
    V2_APP_CHIRPUI_PY,
    V2_APP_PY,
    V2_CONFTEST_PY,
    V2_DASHBOARD_CHIRPUI_HTML,
    V2_DASHBOARD_HTML,
    V2_DASHBOARD_PAGE_PY,
    V2_INDEX_CHIRPUI_HTML,
    V2_INDEX_HTML,
    V2_INDEX_PAGE_PY,
    V2_LAYOUT_CHIRPUI_HTML,
    V2_LAYOUT_HTML,
    V2_LOGIN_CHIRPUI_HTML,
    V2_LOGIN_HTML,
    V2_LOGIN_PAGE_PY,
    V2_MODELS_PY,
    V2_STYLE_CHIRPUI_CSS,
    V2_STYLE_CSS,
    V2_TEST_APP_PY,
)

__all__ = [
    "APP_PY",
    "BASE_HTML",
    "INDEX_HTML",
    "MINIMAL_APP_PY",
    "MINIMAL_INDEX_HTML",
    "SHELL_APP_PY",
    "SHELL_CONTEXT_PY",
    "SHELL_ITEMS_LAYOUT_HTML",
    "SHELL_ITEMS_PAGE_HTML",
    "SHELL_ITEMS_PAGE_PY",
    "SHELL_LAYOUT_CHIRPUI_HTML",
    "SHELL_LAYOUT_HTML",
    "SHELL_PAGE_HTML",
    "SHELL_PAGE_PY",
    "SSE_APP_PY",
    "SSE_INDEX_HTML",
    "STYLE_CSS",
    "TEST_APP_PY",
    "V2_APP_CHIRPUI_PY",
    "V2_APP_PY",
    "V2_CONFTEST_PY",
    "V2_DASHBOARD_CHIRPUI_HTML",
    "V2_DASHBOARD_HTML",
    "V2_DASHBOARD_PAGE_PY",
    "V2_INDEX_CHIRPUI_HTML",
    "V2_INDEX_HTML",
    "V2_INDEX_PAGE_PY",
    "V2_LAYOUT_CHIRPUI_HTML",
    "V2_LAYOUT_HTML",
    "V2_LOGIN_CHIRPUI_HTML",
    "V2_LOGIN_HTML",
    "V2_LOGIN_PAGE_PY",
    "V2_MODELS_PY",
    "V2_STYLE_CHIRPUI_CSS",
    "V2_STYLE_CSS",
    "V2_TEST_APP_PY",
]
