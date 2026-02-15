"""``chirp new`` — project scaffolding command.

Creates a new chirp project directory with starter files.  Two modes:

- **Default**: ``app.py``, ``templates/base.html``, ``templates/index.html``,
  ``static/style.css``, ``tests/test_app.py``
- **Minimal** (``--minimal``): ``app.py``, ``templates/index.html``
"""

import argparse
import sys
from pathlib import Path

from chirp.cli._templates import (
    APP_PY,
    BASE_HTML,
    INDEX_HTML,
    MINIMAL_APP_PY,
    MINIMAL_INDEX_HTML,
    SSE_APP_PY,
    SSE_INDEX_HTML,
    STYLE_CSS,
    TEST_APP_PY,
)


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
        _create_full(project_dir, args.name)

    print(f"Created project '{args.name}'")


def _create_full(project_dir: Path, name: str) -> None:
    """Generate the full project layout."""
    templates_dir = project_dir / "templates"
    static_dir = project_dir / "static"
    tests_dir = project_dir / "tests"

    templates_dir.mkdir(parents=True)
    static_dir.mkdir(parents=True)
    tests_dir.mkdir(parents=True)

    (project_dir / "app.py").write_text(APP_PY)
    (templates_dir / "base.html").write_text(BASE_HTML.format(name=name))
    (templates_dir / "index.html").write_text(INDEX_HTML.format(name=name))
    (static_dir / "style.css").write_text(STYLE_CSS.format(name=name))
    (tests_dir / "test_app.py").write_text(TEST_APP_PY.format(name=name))


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
    (templates_dir / "index.html").write_text(SSE_INDEX_HTML.format(name=name))
    (static_dir / "style.css").write_text(STYLE_CSS.format(name=name))
    (tests_dir / "test_app.py").write_text(TEST_APP_PY.format(name=name))
