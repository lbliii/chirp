"""``chirp new`` — project scaffolding command.

Creates a new chirp project directory with starter files.  Modes include:

- **Default** (v2): Auth + dashboard + primitives (filesystem routing, pages/)
- **Minimal** (``--minimal``): ``app.py``, ``templates/index.html``
- **SSE** (``--sse``): SSE boilerplate
- **Skill** (``--skill``): signed ``skill.tool`` app + secure stack
"""

import argparse
import json
import platform
import re
import sys
from pathlib import Path

from chirp.cli.templates import (
    AGENTS_MD,
    AI_APP_PY,
    AI_CHAT_HTML,
    AI_ENV_EXAMPLE,
    AI_TEST_APP_PY,
    BASE_CSS,
    COMPONENTS_CSS,
    INTERACTIONS_JS,
    MIGRATIONS_README,
    MINIMAL_APP_PY,
    MINIMAL_INDEX_HTML,
    PAGES_CSS,
    PATTERNS_CSS,
    PYPROJECT_TOML,
    RAILWAY_JSON,
    SHELL_APP_PY,
    SHELL_CONTEXT_PY,
    SHELL_ITEMS_LAYOUT_HTML,
    SHELL_ITEMS_PAGE_HTML,
    SHELL_ITEMS_PAGE_PY,
    SHELL_LAYOUT_CHIRPUI_HTML,
    SHELL_LAYOUT_HTML,
    SHELL_PAGE_HTML,
    SHELL_PAGE_PY,
    SKILL_APP_PY,
    SKILL_ENV_EXAMPLE,
    SKILL_INDEX_HTML,
    SKILL_PYPROJECT_TOML,
    SKILL_TEST_APP_PY,
    SSE_APP_PY,
    SSE_INDEX_HTML,
    STREAM_APP_PY,
    STREAM_CONFTEST_PY,
    STREAM_INDEX_HTML,
    STREAM_RESPONSE_HTML,
    STREAM_SSE_PANEL_HTML,
    STREAM_TEST_APP_PY,
    STYLE_CSS,
    TEST_APP_PY,
    THEME_CSS_STUB,
    THEME_JS,
    THEME_PY,
    TOKENS_CSS,
    V2_APP_CHIRPUI_PY,
    V2_APP_PY,
    V2_CONFTEST_PY,
    V2_CONTEXT_PY,
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
    V2_PANEL_COMPONENT_HTML,
    V2_PATTERN_ACCOUNT_SUMMARY_HTML,
    V2_STYLE_CHIRPUI_CSS,
    V2_TEST_APP_PY,
)
from chirp.cli.templates.scaffold import PROJECT_PATHS_PY, PROJECT_README
from chirp.cli.templates.shell import (
    SHELL_APP_CHIRPUI_PY,
    SHELL_ITEMS_PAGE_CHIRPUI_HTML,
    SHELL_ITEMS_PAGE_CHIRPUI_PY,
    SHELL_PAGE_CHIRPUI_HTML,
    SHELL_PAGE_CHIRPUI_PY,
)


def _has_chirpui() -> bool:
    """Return True if chirp-ui is installed."""
    try:
        import chirp_ui  # noqa: F401

        return True
    except ImportError:
        return False


def _write_app_theme_assets(static_dir: Path) -> None:
    """Write app-owned CSS layers + theme/interaction scripts (#858)."""
    css_dir = static_dir / "css"
    js_dir = static_dir / "js"
    css_dir.mkdir(parents=True, exist_ok=True)
    js_dir.mkdir(parents=True, exist_ok=True)
    (css_dir / "tokens.css").write_text(TOKENS_CSS, encoding="utf-8")
    (css_dir / "base.css").write_text(BASE_CSS, encoding="utf-8")
    (css_dir / "components.css").write_text(COMPONENTS_CSS, encoding="utf-8")
    (css_dir / "patterns.css").write_text(PATTERNS_CSS, encoding="utf-8")
    (css_dir / "pages.css").write_text(PAGES_CSS, encoding="utf-8")
    (js_dir / "theme.js").write_text(THEME_JS, encoding="utf-8")
    (js_dir / "interactions.js").write_text(INTERACTIONS_JS, encoding="utf-8")


def _write_scaffold_extras(project_dir: Path, name: str) -> None:
    """pyproject.toml, migrations/, optional theme.css hook."""
    (project_dir / "AGENTS.md").write_text(AGENTS_MD, encoding="utf-8")
    (project_dir / "pyproject.toml").write_text(
        PYPROJECT_TOML.format(name=name),
        encoding="utf-8",
    )
    (project_dir / "railway.json").write_text(RAILWAY_JSON, encoding="utf-8")
    mig = project_dir / "migrations"
    mig.mkdir(exist_ok=True)
    (mig / ".gitkeep").write_text("", encoding="utf-8")
    (mig / "README.md").write_text(MIGRATIONS_README, encoding="utf-8")


def _finish_project_metadata(project_dir: Path, args: argparse.Namespace) -> None:
    """Make each profile's flat source tree explicit to the build backend."""
    (project_dir / "README.md").write_text(PROJECT_README.format(name=args.name), encoding="utf-8")
    (project_dir / ".python-version").write_text(platform.python_version() + "\n", encoding="utf-8")
    (project_dir / "project_paths.py").write_text(
        PROJECT_PATHS_PY.format(
            name=args.name, asset_dir="pages" if (project_dir / "pages").exists() else "templates"
        ),
        encoding="utf-8",
    )
    metadata = project_dir / "pyproject.toml"
    source = metadata.read_text(encoding="utf-8")
    extras = ["sessions"]
    if (project_dir / "models.py").exists():
        extras.extend(["auth", "forms"])
    if getattr(args, "ai", False):
        extras.extend(["ai", "forms"])
    if getattr(args, "stream", False):
        extras.append("forms")
    if getattr(args, "skill", False):
        extras.append("skill")
    if getattr(args, "with_chirpui", False):
        extras.append("ui")
    source = re.sub(r"bengal-chirp\[[^]]+\]", "bengal-chirp[" + ",".join(extras) + "]", source)
    source += (
        '\n[dependency-groups]\ndev = ["pytest>=8,<10", "pytest-asyncio>=1,<2", "httpx>=0.27,<1"]\n'
    )
    source += '\n[tool.pytest.ini_options]\nasyncio_mode = "auto"\n'
    modules = sorted(path.stem for path in project_dir.glob("*.py"))
    source += "\n[tool.setuptools]\npackages = []\npy-modules = " + json.dumps(modules) + "\n"
    source += "\n[tool.setuptools.data-files]\n"
    for directory in sorted(project_dir.rglob("*")):
        if not directory.is_dir() or directory.parts[-1] == "tests":
            continue
        files = sorted(
            str(path.relative_to(project_dir)) for path in directory.iterdir() if path.is_file()
        )
        if files:
            source += (
                json.dumps("share/" + args.name + "/" + str(directory.relative_to(project_dir)))
                + " = "
                + json.dumps(files)
                + "\n"
            )
    metadata.write_text(source, encoding="utf-8")


def create_project(args: argparse.Namespace) -> None:
    """Generate a new chirp project directory.

    Creates the project at ``./<args.name>/`` relative to cwd.
    Refuses to overwrite an existing directory.
    """
    if getattr(args, "with_chirpui", False) and not _has_chirpui():
        print(
            "Error: --with-chirpui requires chirp-ui (pip install 'chirp[ui]' or chirp-ui)",
            file=sys.stderr,
        )
        raise SystemExit(1)

    project_dir = Path(args.name)

    if project_dir.exists():
        print(
            f"Error: directory '{args.name}' already exists",
            file=sys.stderr,
        )
        raise SystemExit(1)

    if args.minimal:
        _create_minimal(project_dir, args.name)
    elif getattr(args, "ai", False):
        _create_ai(project_dir, args.name)
    elif getattr(args, "skill", False):
        _create_skill(project_dir, args.name)
    elif getattr(args, "stream", False):
        _create_stream(project_dir, args.name)
    elif getattr(args, "sse", False):
        _create_sse(project_dir, args.name)
    elif getattr(args, "shell", False):
        _create_shell(
            project_dir,
            args.name,
            with_chirpui=getattr(args, "with_chirpui", False),
        )
    else:
        _create_v2(
            project_dir,
            args.name,
            with_chirpui=getattr(args, "with_chirpui", False),
        )

    _finish_project_metadata(project_dir, args)

    print(f"Created project '{args.name}'")
    if getattr(args, "skill", False):
        print()
        print(f"  cd {args.name} && python app.py")
        print()
        print("  Skill tools: echo (signed Envelope via use_skill)")
        print("  Set CHIRP_SKILL_PRIVATE_KEY for a stable signing key")
    elif (
        not args.minimal
        and not getattr(args, "sse", False)
        and not getattr(args, "stream", False)
        and not getattr(args, "shell", False)
        and not getattr(args, "ai", False)
    ):
        print()
        print(f"  cd {args.name} && python app.py")
        print()
        print("  Login: admin / password")
        print("  Dashboard: http://localhost:8000/dashboard")


def _create_v2(project_dir: Path, name: str, *, with_chirpui: bool) -> None:
    """Generate the v2 project layout (auth + dashboard + primitives)."""
    use_chirpui = with_chirpui
    pages_dir = project_dir / "pages"
    static_dir = project_dir / "static"
    tests_dir = project_dir / "tests"
    templates_dir = project_dir / "templates"

    project_dir.mkdir(parents=True)
    (project_dir / "models.py").write_text(V2_MODELS_PY)
    pages_dir.mkdir(parents=True)
    static_dir.mkdir(parents=True)
    tests_dir.mkdir(parents=True)
    if not use_chirpui:
        (templates_dir / "components" / "chrome").mkdir(parents=True)
        (templates_dir / "patterns").mkdir(parents=True)
        (templates_dir / "_partials").mkdir(parents=True)

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

    if not use_chirpui:
        (templates_dir / "components" / "chrome" / "panel.html").write_text(
            V2_PANEL_COMPONENT_HTML,
        )
        (templates_dir / "patterns" / "account_summary.html").write_text(
            V2_PATTERN_ACCOUNT_SUMMARY_HTML,
        )
        (templates_dir / "_partials" / ".gitkeep").write_text("")
        (project_dir / "theme.py").write_text(THEME_PY, encoding="utf-8")
        (pages_dir / "_context.py").write_text(V2_CONTEXT_PY, encoding="utf-8")
        _write_app_theme_assets(static_dir)
    else:
        style = V2_STYLE_CHIRPUI_CSS
        (static_dir / "style.css").write_text(style.format())

    (tests_dir / "conftest.py").write_text(V2_CONFTEST_PY)
    (tests_dir / "test_app.py").write_text(V2_TEST_APP_PY.format(name=name))

    _write_scaffold_extras(project_dir, name)
    if use_chirpui:
        (static_dir / "theme.css").write_text(THEME_CSS_STUB, encoding="utf-8")


def _create_shell(project_dir: Path, name: str, *, with_chirpui: bool) -> None:
    """Generate project with persistent app shell (topbar, sidebar)."""
    use_chirpui = with_chirpui
    pages_dir = project_dir / "pages"
    static_dir = project_dir / "static"

    project_dir.mkdir(parents=True)
    pages_dir.mkdir(parents=True)
    static_dir.mkdir(parents=True)

    (project_dir / "app.py").write_text(SHELL_APP_CHIRPUI_PY if use_chirpui else SHELL_APP_PY)
    (pages_dir / "_context.py").write_text(SHELL_CONTEXT_PY)
    (pages_dir / "_layout.html").write_text(
        SHELL_LAYOUT_CHIRPUI_HTML if use_chirpui else SHELL_LAYOUT_HTML,
    )
    (pages_dir / "page.py").write_text(SHELL_PAGE_CHIRPUI_PY if use_chirpui else SHELL_PAGE_PY)
    (pages_dir / "page.html").write_text(
        SHELL_PAGE_CHIRPUI_HTML if use_chirpui else SHELL_PAGE_HTML
    )

    items_dir = pages_dir / "items"
    items_dir.mkdir()
    if not use_chirpui:
        (items_dir / "_layout.html").write_text(SHELL_ITEMS_LAYOUT_HTML)
    (items_dir / "page.py").write_text(
        SHELL_ITEMS_PAGE_CHIRPUI_PY if use_chirpui else SHELL_ITEMS_PAGE_PY
    )
    (items_dir / "page.html").write_text(
        SHELL_ITEMS_PAGE_CHIRPUI_HTML if use_chirpui else SHELL_ITEMS_PAGE_HTML
    )

    (project_dir / "theme.py").write_text(THEME_PY, encoding="utf-8")
    _write_scaffold_extras(project_dir, name)
    if use_chirpui:
        (static_dir / "theme.css").write_text(THEME_CSS_STUB, encoding="utf-8")
    else:
        _write_app_theme_assets(static_dir)


def _create_minimal(project_dir: Path, name: str) -> None:
    """Generate the minimal project layout."""
    templates_dir = project_dir / "templates"
    templates_dir.mkdir(parents=True)

    (project_dir / "app.py").write_text(MINIMAL_APP_PY)
    (templates_dir / "index.html").write_text(MINIMAL_INDEX_HTML.format(name=name))

    _write_scaffold_extras(project_dir, name)


def _create_ai(project_dir: Path, name: str) -> None:
    """Generate AI chat scaffold with tools and SSE activity."""
    templates_dir = project_dir / "templates"
    tests_dir = project_dir / "tests"
    templates_dir.mkdir(parents=True)
    tests_dir.mkdir(parents=True)

    (project_dir / "app.py").write_text(AI_APP_PY)
    (templates_dir / "chat.html").write_text(AI_CHAT_HTML)
    (project_dir / ".env.example").write_text(AI_ENV_EXAMPLE)
    (tests_dir / "test_app.py").write_text(AI_TEST_APP_PY.format(name=name))
    _write_scaffold_extras(project_dir, name)


def _create_skill(project_dir: Path, name: str) -> None:
    """Generate a signed skill app (skill.tool + secure stack + Railway)."""
    templates_dir = project_dir / "templates"
    tests_dir = project_dir / "tests"
    templates_dir.mkdir(parents=True)
    tests_dir.mkdir(parents=True)

    (project_dir / "app.py").write_text(SKILL_APP_PY, encoding="utf-8")
    (templates_dir / "index.html").write_text(SKILL_INDEX_HTML, encoding="utf-8")
    (project_dir / ".env.example").write_text(SKILL_ENV_EXAMPLE, encoding="utf-8")
    (tests_dir / "test_app.py").write_text(
        SKILL_TEST_APP_PY.format(name=name),
        encoding="utf-8",
    )
    _write_scaffold_extras(project_dir, name)
    (project_dir / "pyproject.toml").write_text(
        SKILL_PYPROJECT_TOML.format(name=name),
        encoding="utf-8",
    )


def _create_stream(project_dir: Path, name: str) -> None:
    """Generate simulated token streaming demo (TemplateStream + EventStream)."""
    templates_dir = project_dir / "templates"
    tests_dir = project_dir / "tests"
    templates_dir.mkdir(parents=True)
    tests_dir.mkdir(parents=True)

    (project_dir / "app.py").write_text(STREAM_APP_PY.format(name=name), encoding="utf-8")
    (templates_dir / "index.html").write_text(STREAM_INDEX_HTML, encoding="utf-8")
    (templates_dir / "response.html").write_text(STREAM_RESPONSE_HTML, encoding="utf-8")
    (templates_dir / "sse_panel.html").write_text(STREAM_SSE_PANEL_HTML, encoding="utf-8")
    (tests_dir / "conftest.py").write_text(STREAM_CONFTEST_PY, encoding="utf-8")
    (tests_dir / "test_app.py").write_text(STREAM_TEST_APP_PY.format(name=name), encoding="utf-8")
    _write_scaffold_extras(project_dir, name)


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

    _write_scaffold_extras(project_dir, name)
