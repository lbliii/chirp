"""``chirp new`` — project scaffolding command.

Creates a new chirp project directory with starter files.  Three modes:

- **Default** (v2): Auth + dashboard + primitives (filesystem routing, pages/)
- **Minimal** (``--minimal``): ``app.py``, ``templates/index.html``
- **SSE** (``--sse``): SSE boilerplate
"""

import argparse
import sys
from pathlib import Path

from chirp.cli._templates import (
    MINIMAL_APP_PY,
    MINIMAL_INDEX_HTML,
    SSE_APP_PY,
    SSE_INDEX_HTML,
    STYLE_CSS,
    TEST_APP_PY,
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


def _has_chirpui() -> bool:
    """Return True if chirp-ui is installed."""
    try:
        import chirp_ui  # noqa: F401

        return True
    except ImportError:
        return False


def create_project(args: argparse.Namespace) -> None:
    """Generate a new chirp project directory.

    Creates the project at ``./<args.name>/`` relative to cwd.
    Refuses to overwrite an existing directory.
    """
    project_dir = Path(args.name)

    if project_dir.exists():
        print(
            f"Error: directory '{args.name}' already exists",
            file=sys.stderr,
        )
        raise SystemExit(1)

    if args.minimal:
        _create_minimal(project_dir, args.name)
    elif getattr(args, "sse", False):
        _create_sse(project_dir, args.name)
    else:
        _create_v2(project_dir, args.name)

    print(f"Created project '{args.name}'")
    if not args.minimal and not getattr(args, "sse", False):
        print()
        print(f"  cd {args.name} && python app.py")
        print()
        print("  Login: admin / password")
        print("  Dashboard: http://localhost:8000/dashboard")


def _create_v2(project_dir: Path, name: str) -> None:
    """Generate the v2 project layout (auth + dashboard + primitives)."""
    use_chirpui = _has_chirpui()
    pages_dir = project_dir / "pages"
    static_dir = project_dir / "static"
    tests_dir = project_dir / "tests"

    project_dir.mkdir(parents=True)
    (project_dir / "models.py").write_text(V2_MODELS_PY)
    pages_dir.mkdir(parents=True)
    static_dir.mkdir(parents=True)
    tests_dir.mkdir(parents=True)

    if use_chirpui:
        (project_dir / "app.py").write_text(V2_APP_CHIRPUI_PY)
    else:
        (project_dir / "app.py").write_text(V2_APP_PY)

    (pages_dir / "_layout.html").write_text(
        V2_LAYOUT_CHIRPUI_HTML if use_chirpui else V2_LAYOUT_HTML,
    )
    (pages_dir / "page.py").write_text(V2_INDEX_PAGE_PY)
    (pages_dir / "page.html").write_text(
        V2_INDEX_CHIRPUI_HTML if use_chirpui else V2_INDEX_HTML,
    )

    login_dir = pages_dir / "login"
    login_dir.mkdir()
    (login_dir / "page.py").write_text(V2_LOGIN_PAGE_PY)
    (login_dir / "page.html").write_text(
        V2_LOGIN_CHIRPUI_HTML if use_chirpui else V2_LOGIN_HTML,
    )

    dashboard_dir = pages_dir / "dashboard"
    dashboard_dir.mkdir()
    (dashboard_dir / "page.py").write_text(V2_DASHBOARD_PAGE_PY)
    (dashboard_dir / "page.html").write_text(
        V2_DASHBOARD_CHIRPUI_HTML if use_chirpui else V2_DASHBOARD_HTML,
    )

    (static_dir / "style.css").write_text(
        V2_STYLE_CHIRPUI_CSS if use_chirpui else V2_STYLE_CSS,
    )

    (tests_dir / "conftest.py").write_text(V2_CONFTEST_PY)
    (tests_dir / "test_app.py").write_text(V2_TEST_APP_PY.format(name=name))


def _create_minimal(project_dir: Path, name: str) -> None:
    """Generate the minimal project layout."""
    templates_dir = project_dir / "templates"
    templates_dir.mkdir(parents=True)

    (project_dir / "app.py").write_text(MINIMAL_APP_PY)
    (templates_dir / "index.html").write_text(MINIMAL_INDEX_HTML.format(name=name))


def _create_sse(project_dir: Path, name: str) -> None:
    """Generate project with SSE boilerplate."""
    templates_dir = project_dir / "templates"
    static_dir = project_dir / "static"
    tests_dir = project_dir / "tests"

    templates_dir.mkdir(parents=True)
    static_dir.mkdir(parents=True)
    tests_dir.mkdir(parents=True)

    (project_dir / "app.py").write_text(SSE_APP_PY)
    (templates_dir / "index.html").write_text(SSE_INDEX_HTML)
    (static_dir / "style.css").write_text(STYLE_CSS.format(name=name))
    (tests_dir / "test_app.py").write_text(TEST_APP_PY.format(name=name))
