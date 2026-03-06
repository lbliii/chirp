"""End-to-end tests for route-scoped shell actions in mounted pages apps."""

from pathlib import Path

from chirp import App, AppConfig
from chirp.testing import TestClient


def _create_shell_actions_app(tmp_path: Path) -> App:
    pages_dir = tmp_path / "pages"
    pages_dir.mkdir()
    (pages_dir / "forum").mkdir()
    (pages_dir / "forum" / "thread").mkdir()
    (pages_dir / "forum" / "archived").mkdir()

    (pages_dir / "_layout.html").write_text(
        '{% from "chirpui/shell_actions.html" import shell_actions_bar %}'
        '{% set shell_actions_target = shell_actions.target if shell_actions is defined and shell_actions else "chirp-shell-actions" %}'
        '<div class="chirpui-app-shell">'
        '<header class="chirpui-app-shell__topbar">'
        '<a href="/" class="chirpui-app-shell__brand">Forum</a>'
        '<div class="chirpui-app-shell__topbar-center"><span>Forum</span></div>'
        '<div class="chirpui-app-shell__topbar-end">'
        '<div id="{{ shell_actions_target }}" class="chirpui-app-shell__shell-actions">'
        "{% if shell_actions is defined %}{{ shell_actions_bar(shell_actions) }}{% end %}"
        "</div>"
        "</div>"
        "</header>"
        '<aside class="chirpui-app-shell__sidebar"><nav>Sidebar</nav></aside>'
        '<main id="main" class="chirpui-app-shell__main" hx-boost="true" hx-target="#main" hx-swap="innerHTML transition:true" hx-select="#page-content">'
        '<div id="page-content">{% block content %}{% end %}</div>'
        "</main>"
        "</div>",
        encoding="utf-8",
    )

    (pages_dir / "forum" / "_context.py").write_text(
        """
from chirp import ShellAction, ShellActions, ShellActionZone


def context() -> dict:
    return {
        "shell_actions": ShellActions(
            primary=ShellActionZone(
                items=(ShellAction(id="new-thread", label="New thread", href="/forum/new"),)
            )
        )
    }
""",
        encoding="utf-8",
    )

    (pages_dir / "forum" / "page.py").write_text(
        """
from chirp import Page


def handler() -> Page:
    return Page("forum/page.html", "content")
""",
        encoding="utf-8",
    )
    (pages_dir / "forum" / "page.html").write_text(
        "{% block content %}<h1>Forum Index</h1><p>Root forum page.</p>{% end %}",
        encoding="utf-8",
    )

    (pages_dir / "forum" / "thread" / "_context.py").write_text(
        """
from chirp import ShellAction, ShellActions, ShellActionZone


def context() -> dict:
    return {
        "shell_actions": ShellActions(
            primary=ShellActionZone(
                items=(ShellAction(id="reply", label="Reply", href="/forum/thread/reply"),),
                remove=("new-thread",),
            )
        )
    }
""",
        encoding="utf-8",
    )
    (pages_dir / "forum" / "thread" / "page.py").write_text(
        """
from chirp import Page


def handler() -> Page:
    return Page("forum/thread/page.html", "content")
""",
        encoding="utf-8",
    )
    (pages_dir / "forum" / "thread" / "page.html").write_text(
        "{% block content %}<h1>Thread</h1><p>Thread detail page.</p>{% end %}",
        encoding="utf-8",
    )

    (pages_dir / "forum" / "archived" / "_context.py").write_text(
        """
from chirp import ShellActions, ShellActionZone


def context() -> dict:
    return {
        "shell_actions": ShellActions(
            primary=ShellActionZone(mode="replace"),
            controls=ShellActionZone(mode="replace"),
            overflow=ShellActionZone(mode="replace"),
        )
    }
""",
        encoding="utf-8",
    )
    (pages_dir / "forum" / "archived" / "page.py").write_text(
        """
from chirp import Page


def handler() -> Page:
    return Page("forum/archived/page.html", "content")
""",
        encoding="utf-8",
    )
    (pages_dir / "forum" / "archived" / "page.html").write_text(
        "{% block content %}<h1>Archived</h1><p>No shell actions here.</p>{% end %}",
        encoding="utf-8",
    )

    app = App(AppConfig(template_dir=str(pages_dir), debug=True))
    app.mount_pages(str(pages_dir))
    return app


class TestShellActionsMountedPages:
    async def test_boosted_navigation_updates_and_clears_shell_actions(
        self, tmp_path: Path
    ) -> None:
        app = _create_shell_actions_app(tmp_path)

        async with TestClient(app) as client:
            full_response = await client.get("/forum")
            assert full_response.status == 200
            assert 'id="chirp-shell-actions"' in full_response.text
            assert "New thread" in full_response.text

            thread_response = await client.fragment(
                "/forum/thread",
                target="main",
                headers={"HX-Boosted": "true"},
            )
            assert thread_response.status == 200
            assert "<h1>Thread</h1>" in thread_response.text
            assert 'id="chirp-shell-actions"' in thread_response.text
            assert 'hx-swap-oob="innerHTML"' in thread_response.text
            assert "Reply" in thread_response.text
            assert "New thread" not in thread_response.text

            archived_response = await client.fragment(
                "/forum/archived",
                target="main",
                headers={"HX-Boosted": "true"},
            )
            assert archived_response.status == 200
            assert "<h1>Archived</h1>" in archived_response.text
            assert (
                '<div id="chirp-shell-actions" hx-swap-oob="innerHTML">' in archived_response.text
            )
            assert "Reply" not in archived_response.text
            assert "New thread" not in archived_response.text
