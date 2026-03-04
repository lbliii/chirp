"""Integration test: Dori-style app (mount_pages + GET form + POST+htmx + SSE) passes app.check()."""

import importlib.util
from pathlib import Path

import pytest

from chirp import App, AppConfig, EventStream, Fragment, Request, SSEEvent


def _create_dori_pattern_app(tmp_path: Path) -> App:
    """Create minimal Chirp app mirroring Dori dashboard patterns."""
    pages_dir = tmp_path / "pages"
    pages_dir.mkdir()
    (pages_dir / "skills").mkdir()

    # Layout with block page_content (Dori-style)
    (pages_dir / "_layout.html").write_text(
        '<html><body id="main">{% block page_content %}{% end %}</body></html>'
    )

    # /skills page with plain GET form (Dori skills search)
    (pages_dir / "skills" / "page.py").write_text(
        '''
from chirp import Template

async def handler():
    return Template("skills/page.html", skills=[], q="")
'''
    )
    (pages_dir / "skills" / "page.html").write_text(
        '{% block page_content %}'
        '<form action="/skills" method="get">'
        '<input type="search" name="q" value="{{ q }}">'
        '<button type="submit">Search</button></form>'
        '{% end %}'
    )

    # Root page
    (pages_dir / "page.py").write_text(
        '''
from chirp import Template

async def handler():
    return Template("page.html")
'''
    )
    (pages_dir / "page.html").write_text(
        '{% block page_content %}<h1>Home</h1>'
        '<form action="/exec" method="post" hx-post="/exec" hx-target="#result">'
        '<input name="skill" value="test"><button>Run</button></form>'
        '<div id="result"></div>{% end %}'
    )

    app = App(AppConfig(template_dir=str(pages_dir), debug=True))
    app.mount_pages(str(pages_dir))

    @app.route("/exec", methods=["POST"])
    async def post_exec(request: Request) -> Fragment:
        return Fragment("page.html", "exec_result", text="ok")

    @app.route("/exec/stream", methods=["GET"], referenced=True)
    async def exec_stream(request: Request) -> EventStream:
        async def gen():
            yield Fragment("page.html", "exec_result", text="streaming")
            yield SSEEvent(event="done", data="complete")

        return EventStream(gen())

    # Add exec_result block to page.html for Fragment
    (pages_dir / "page.html").write_text(
        '{% block page_content %}<h1>Home</h1>'
        '<form action="/exec" method="post" hx-post="/exec" hx-target="#result">'
        '<input name="skill" value="test"><button>Run</button></form>'
        '<div id="result"></div>{% end %}'
        '{% block exec_result %}<p>{{ text }}</p>{% end %}'
    )

    return app


class TestDoriPatterns:
    """Dori-style app patterns pass contract validation."""

    def test_dori_pattern_app_passes_check(self, tmp_path: Path) -> None:
        """mount_pages + GET form + POST+htmx + SSE passes app.check()."""
        app = _create_dori_pattern_app(tmp_path)
        app.check()

    def test_form_get_example_passes_check(self) -> None:
        """form_get example (plain form action + method=get) passes chirp check."""
        app_path = Path(__file__).resolve().parent.parent / "examples" / "form_get" / "app.py"
        if not app_path.exists():
            pytest.skip("examples/form_get not found")
        spec = importlib.util.spec_from_file_location("form_get_app", app_path)
        assert spec is not None
        assert spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        app = module.app
        app.check()
