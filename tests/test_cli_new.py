"""Tests for chirp.cli._new — ``chirp new`` subcommand."""

import json
from pathlib import Path

import pytest

from chirp.cli import main


@pytest.mark.issue(736)
@pytest.mark.parametrize(
    "mode_args",
    [
        [],
        ["--minimal"],
        ["--sse"],
        ["--shell"],
        ["--stream"],
        ["--ai"],
        ["--skill"],
    ],
    ids=["v2", "minimal", "sse", "shell", "stream", "ai", "skill"],
)
def test_generated_apps_ship_railway_runtime_contract(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mode_args: list[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    main(["new", "myapp", *mode_args])

    project = tmp_path / "myapp"
    source = (project / "app.py").read_text()
    config = json.loads((project / "railway.json").read_text())

    assert "AppConfig.from_env(" in source
    assert 'if __name__ == "__main__":' in source
    assert "app.run()" in source
    assert config == {
        "$schema": "https://railway.com/railway.schema.json",
        "build": {"builder": "RAILPACK"},
        "deploy": {
            "startCommand": "python app.py",
            "healthcheckPath": "/ready",
            "healthcheckTimeout": 100,
            "restartPolicyType": "ON_FAILURE",
            "restartPolicyMaxRetries": 10,
        },
    }


def test_templates_shim_import() -> None:
    """chirp.cli._templates re-exports from chirp.cli.templates for backward compat."""
    from chirp.cli._templates import STYLE_CSS, V2_APP_PY

    assert "box-sizing" in STYLE_CSS
    assert "App(" in V2_APP_PY


class TestChirpNewDefaultV2:
    def test_creates_expected_v2_tree(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Default scaffold (v2) creates pages/, static/, tests/, models.py."""
        monkeypatch.chdir(tmp_path)
        main(["new", "myapp"])

        project = tmp_path / "myapp"
        assert (project / "app.py").is_file()
        assert (project / "models.py").is_file()
        assert (project / "pages" / "_layout.html").is_file()
        assert (project / "pages" / "page.py").is_file()
        assert (project / "pages" / "page.html").is_file()
        assert (project / "pages" / "login" / "page.py").is_file()
        assert (project / "pages" / "login" / "page.html").is_file()
        assert (project / "pages" / "dashboard" / "page.py").is_file()
        assert (project / "pages" / "dashboard" / "page.html").is_file()
        assert (project / "templates" / "components" / "chrome" / "panel.html").is_file()
        assert (project / "templates" / "patterns" / "account_summary.html").is_file()
        assert (project / "templates" / "_partials" / ".gitkeep").is_file()
        assert (project / "static" / "css" / "tokens.css").is_file()
        assert (project / "static" / "js" / "theme.js").is_file()
        assert (project / "theme.py").is_file()
        assert not (project / "static" / "style.css").exists()
        assert not (project / "static" / "theme.css").exists()
        assert (project / "AGENTS.md").is_file()
        assert (project / "pyproject.toml").is_file()
        assert (project / "railway.json").is_file()
        assert (project / "migrations" / ".gitkeep").is_file()
        assert (project / "tests" / "conftest.py").is_file()
        assert (project / "tests" / "test_app.py").is_file()

    def test_generated_v2_app_contains_security_defaults(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        main(["new", "myapp"])

        source = (tmp_path / "myapp" / "app.py").read_text()
        assert "CHIRP_SECRET_KEY" in source
        assert "Refusing to start in production with default secret key" in source
        # The old `secure=not config.debug` band-aid is gone — secure now
        # relies on the "auto" default (Secure in prod/staging via AppConfig.env).
        assert "secure=not config.debug" not in source
        assert "env=_env" in source
        assert "CHIRP_ENV" in source
        assert "AppConfig.from_env(" in source
        assert "secure_stack(config" in source
        assert "app.add_middleware(middleware)" in source
        assert "from chirp import secure_stack" in source

    def test_generated_v2_chirpui_layout_loads_theme_override_slot(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from chirp.cli import _new

        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(_new, "_has_chirpui", lambda: True)
        main(["new", "myapp", "--with-chirpui"])

        layout = (tmp_path / "myapp" / "pages" / "_layout.html").read_text()
        assert "/static/chirpui.css" in layout
        assert "/static/theme.css" in layout
        assert layout.index("/static/chirpui.css") < layout.index("/static/theme.css")

        theme = (tmp_path / "myapp" / "static" / "theme.css").read_text()
        assert "app-theme-starter.css" in theme

    def test_generated_v2_chirpui_layout_ships_htmx(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The chirpui layout's dashboard uses hx-*/sse-*, so it must ship htmx.

        Regression for #150: a layout emitting hx-*/sse-* with no htmx script
        is dead in a browser. htmx + the SSE extension must be provisioned, in
        the <head> (before the deferred body that uses them).
        """
        from chirp.cli import _new

        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(_new, "_has_chirpui", lambda: True)
        main(["new", "myapp", "--with-chirpui"])

        layout = (tmp_path / "myapp" / "pages" / "_layout.html").read_text()
        assert "htmx.org@" in layout
        assert "htmx-ext-sse@" in layout
        # htmx must be provisioned in the head, before </head>.
        assert layout.index("htmx.org@") < layout.index("</head>")

    def test_generated_v2_files_are_valid_python(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        main(["new", "myapp"])

        app_source = (tmp_path / "myapp" / "app.py").read_text()
        models_source = (tmp_path / "myapp" / "models.py").read_text()
        test_source = (tmp_path / "myapp" / "tests" / "test_app.py").read_text()

        compile(app_source, "app.py", "exec")
        compile(models_source, "models.py", "exec")
        compile(test_source, "test_app.py", "exec")

    def test_prints_success_message_and_login_hint(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.chdir(tmp_path)
        main(["new", "myapp"])

        captured = capsys.readouterr()
        assert "Created project 'myapp'" in captured.out
        assert "Login: admin / password" in captured.out

    def test_generated_agents_md_points_agents_to_devtools(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        main(["new", "myapp"])

        guidance = (tmp_path / "myapp" / "AGENTS.md").read_text()
        assert "chirp dev app:app" in guidance
        assert "window.ChirpHtmxDebug.help()" in guidance
        assert "window.ChirpHtmxDebug.exportRecordsJson()" in guidance


class TestChirpNewMinimal:
    def test_creates_minimal_tree(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """--minimal creates only app.py and templates/index.html."""
        monkeypatch.chdir(tmp_path)
        main(["new", "myapp", "--minimal"])

        project = tmp_path / "myapp"
        assert (project / "app.py").is_file()
        assert (project / "AGENTS.md").is_file()
        assert (project / "templates" / "index.html").is_file()
        assert not (project / "pages").exists()
        assert not (project / "static").exists()
        assert not (project / "tests").exists()

    def test_minimal_app_is_valid_python(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        main(["new", "myapp", "--minimal"])

        source = (tmp_path / "myapp" / "app.py").read_text()
        compile(source, "app.py", "exec")

    def test_generated_minimal_app_contains_security_defaults(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """--minimal wires the full Session/CSRF/SecurityHeaders stack (#183)."""
        monkeypatch.chdir(tmp_path)
        main(["new", "myapp", "--minimal"])

        source = (tmp_path / "myapp" / "app.py").read_text()
        assert "CHIRP_SECRET_KEY" in source
        assert "Refusing to start in production with default secret key" in source
        # The old `secure=not config.debug` band-aid is gone — secure now
        # relies on the "auto" default (Secure in prod/staging via AppConfig.env).
        assert "secure=not config.debug" not in source
        assert "env=_env" in source
        assert "CHIRP_ENV" in source
        assert "AppConfig.from_env(" in source
        assert "secure_stack(config" in source
        assert "app.add_middleware(middleware)" in source
        assert "from chirp import secure_stack" in source


@pytest.mark.issue(437)
class TestChirpNewAI:
    def test_creates_ai_tree(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """--ai creates AgentRun chat scaffold with tools and SSE activity."""
        monkeypatch.chdir(tmp_path)
        main(["new", "myapp", "--ai"])

        project = tmp_path / "myapp"
        assert (project / "app.py").is_file()
        assert (project / "templates" / "chat.html").is_file()
        assert (project / ".env.example").is_file()
        assert (project / "tests" / "test_app.py").is_file()

        source = (project / "app.py").read_text()
        assert "AgentRun" in source
        assert "InMemoryConversationStore" in source
        assert "secure_stack" in source
        compile(source, "app.py", "exec")


@pytest.mark.issue(980)
class TestChirpNewSkill:
    def test_creates_skill_tree(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """--skill creates a signed skill.tool scaffold with secure stack."""
        monkeypatch.chdir(tmp_path)
        main(["new", "myapp", "--skill"])

        project = tmp_path / "myapp"
        assert (project / "app.py").is_file()
        assert (project / "templates" / "index.html").is_file()
        assert (project / ".env.example").is_file()
        assert (project / "tests" / "test_app.py").is_file()
        assert (project / "railway.json").is_file()
        assert (project / "pyproject.toml").is_file()

        source = (project / "app.py").read_text(encoding="utf-8")
        assert "use_skill" in source
        assert "@skill.tool" in source
        assert "secure_stack" in source
        assert "CHIRP_SECRET_KEY" in source
        assert "cryptography" in (project / "pyproject.toml").read_text(encoding="utf-8")
        compile(source, "app.py", "exec")

    def test_generated_skill_app_passes_check(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Scaffold builds and passes app.check() (#980)."""
        import importlib.util
        import sys

        monkeypatch.chdir(tmp_path)
        main(["new", "skillapp", "--skill"])

        monkeypatch.syspath_prepend(str(tmp_path / "skillapp"))
        app_path = tmp_path / "skillapp" / "app.py"
        spec = importlib.util.spec_from_file_location("skillapp_scaffold", app_path)
        assert spec is not None
        assert spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        sys.modules["skillapp_scaffold"] = module
        try:
            spec.loader.exec_module(module)
            module.app.check()  # raises SystemExit(1) on ERROR
        finally:
            sys.modules.pop("skillapp_scaffold", None)
            sys.modules.pop("project_paths", None)


class TestChirpNewStream:
    def test_creates_stream_tree(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        main(["new", "myapp", "--stream"])

        project = tmp_path / "myapp"
        assert (project / "app.py").is_file()
        assert (project / "templates" / "index.html").is_file()
        assert (project / "templates" / "response.html").is_file()
        assert (project / "templates" / "sse_panel.html").is_file()
        assert (project / "tests" / "conftest.py").is_file()
        assert (project / "tests" / "test_app.py").is_file()
        compile((project / "app.py").read_text(), "app.py", "exec")


class TestChirpNewSSE:
    def test_creates_sse_tree(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        main(["new", "myapp", "--sse"])

        project = tmp_path / "myapp"
        assert (project / "app.py").is_file()
        assert (project / "AGENTS.md").is_file()
        assert (project / "templates" / "index.html").is_file()
        assert (project / "static" / "style.css").is_file()
        assert (project / "tests" / "test_app.py").is_file()


class TestChirpNewShell:
    def test_creates_shell_tree(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """--shell creates persistent app shell with layout, items inner shell."""
        monkeypatch.chdir(tmp_path)
        main(["new", "myapp", "--shell"])

        project = tmp_path / "myapp"
        assert (project / "app.py").is_file()
        assert (project / "pages" / "_context.py").is_file()
        assert (project / "pages" / "_layout.html").is_file()
        assert (project / "pages" / "page.py").is_file()
        assert (project / "pages" / "page.html").is_file()
        assert (project / "pages" / "items" / "_layout.html").is_file()
        assert (project / "pages" / "items" / "page.py").is_file()
        assert (project / "pages" / "items" / "page.html").is_file()
        assert (project / "AGENTS.md").is_file()
        assert (project / "pyproject.toml").is_file()
        assert (project / "static" / "css" / "tokens.css").is_file()
        assert (project / "theme.py").is_file()
        assert not (project / "static" / "theme.css").exists()

    def test_shell_app_is_valid_python(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        main(["new", "myapp", "--shell"])

        app_source = (tmp_path / "myapp" / "app.py").read_text()
        context_source = (tmp_path / "myapp" / "pages" / "_context.py").read_text()
        compile(app_source, "app.py", "exec")
        compile(context_source, "_context.py", "exec")

    def test_generated_shell_app_contains_security_defaults(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """--shell wires the full Session/CSRF/SecurityHeaders stack (#183)."""
        monkeypatch.chdir(tmp_path)
        main(["new", "myapp", "--shell"])

        source = (tmp_path / "myapp" / "app.py").read_text()
        assert "CHIRP_SECRET_KEY" in source
        assert "Refusing to start in production with default secret key" in source
        # The old `secure=not config.debug` band-aid is gone — secure now
        # relies on the "auto" default (Secure in prod/staging via AppConfig.env).
        assert "secure=not config.debug" not in source
        assert "env=_env" in source
        assert "CHIRP_ENV" in source
        assert "AppConfig.from_env(" in source
        assert "secure_stack(config" in source
        assert "app.add_middleware(middleware)" in source
        assert "from chirp import secure_stack" in source

    def test_plain_shell_keeps_transition_off_broad_main(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The plain shell scaffold avoids broad View Transitions around live content."""
        from chirp.cli import _new

        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(_new, "_has_chirpui", lambda: False)
        main(["new", "myapp", "--shell"])

        layout = (tmp_path / "myapp" / "pages" / "_layout.html").read_text()
        main_tag = next(line for line in layout.splitlines() if 'id="main"' in line)
        assert "transition:true" not in main_tag


class TestChirpNewGuards:
    def test_existing_directory_exits_one(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Refuse to overwrite an existing directory."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / "myapp").mkdir()

        with pytest.raises(SystemExit) as exc_info:
            main(["new", "myapp"])
        assert exc_info.value.code == 1

        captured = capsys.readouterr()
        assert "already exists" in captured.err
