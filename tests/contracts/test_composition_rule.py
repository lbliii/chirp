"""Page-template-extends-registered-layout contract rule.

Promotes the AGENTS.md anti-pattern bullet ("Adding `extends` to a page
template so it can override layout blocks") into a startup ``app.check()``
WARNING.
"""

from __future__ import annotations

import pytest
from kida import DictLoader, Environment

from chirp.contracts.rules_composition import check_page_extends_layout
from chirp.contracts.types import Severity
from chirp.pages.types import LayoutChain, LayoutInfo


def _env(templates: dict[str, str]) -> Environment:
    return Environment(loader=DictLoader(templates))


def _chain(*template_names: str) -> LayoutChain:
    return LayoutChain(
        layouts=tuple(
            LayoutInfo(template_name=name, target="body" if i == 0 else "app-content", depth=i)
            for i, name in enumerate(template_names)
        )
    )


class TestCompositionRule:
    def test_page_without_extends_is_accepted(self) -> None:
        env = _env(
            {
                "_layout.html": "<html><body>{% block content %}{% end %}</body></html>",
                "page.html": "{% block page_root %}{% block page_content %}hi{% end %}{% end %}",
            }
        )
        issues = check_page_extends_layout({"page.html"}, [_chain("_layout.html")], env)
        assert issues == []

    def test_page_extending_non_layout_partial_is_accepted(self) -> None:
        # The oob_layout_chain pattern: page extends a kida partial, the partial
        # is NOT registered as a layout. This is intentionally allowed.
        env = _env(
            {
                "_layout.html": "<html><body>{% block content %}{% end %}</body></html>",
                "_page_layout.html": (
                    "{% block content %}"
                    "{% block page_root %}{% block page_content %}{% end %}{% end %}"
                    "{% end %}"
                ),
                "page.html": (
                    '{% extends "_page_layout.html" %}{% block page_content %}<p>hi</p>{% end %}'
                ),
            }
        )
        issues = check_page_extends_layout({"page.html"}, [_chain("_layout.html")], env)
        assert issues == []

    def test_page_extending_registered_layout_is_flagged(self) -> None:
        env = _env(
            {
                "_layout.html": (
                    "<html><body>"
                    "{% block content %}{% end %}"
                    "{% block page_scripts %}{% end %}"
                    "</body></html>"
                ),
                "page.html": (
                    '{% extends "_layout.html" %}'
                    "{% block content %}<p>hi</p>{% end %}"
                    "{% block page_scripts %}<script>1</script>{% end %}"
                ),
            }
        )
        issues = check_page_extends_layout({"page.html"}, [_chain("_layout.html")], env)
        assert len(issues) == 1
        issue = issues[0]
        assert issue.severity == Severity.WARNING
        assert issue.category == "composition_extends"
        assert issue.template == "page.html"
        assert "_layout.html" in issue.message
        assert "render_with_blocks" in issue.message
        assert "silently lost" in issue.message
        assert "twice" in issue.message

    def test_multiple_pages_each_flagged_once(self) -> None:
        env = _env(
            {
                "_layout.html": "<html><body>{% block content %}{% end %}</body></html>",
                "a.html": '{% extends "_layout.html" %}{% block content %}A{% end %}',
                "b.html": '{% extends "_layout.html" %}{% block content %}B{% end %}',
            }
        )
        issues = check_page_extends_layout({"a.html", "b.html"}, [_chain("_layout.html")], env)
        assert len(issues) == 2
        assert {i.template for i in issues} == {"a.html", "b.html"}

    def test_page_extending_inner_layout_is_flagged(self) -> None:
        # Two-deep chain. Page extends the *inner* registered layout — also broken.
        env = _env(
            {
                "_layout.html": "<html><body>{% block content %}{% end %}</body></html>",
                "_inner.html": (
                    '{% extends "_layout.html" %}'
                    "{% block content %}{% block page_root %}{% end %}{% end %}"
                ),
                "page.html": ('{% extends "_inner.html" %}{% block page_root %}<p>hi</p>{% end %}'),
            }
        )
        issues = check_page_extends_layout(
            {"page.html"}, [_chain("_layout.html", "_inner.html")], env
        )
        assert len(issues) == 1
        assert "_inner.html" in issues[0].message

    def test_empty_page_leaf_set(self) -> None:
        env = _env({"_layout.html": "<html></html>"})
        assert check_page_extends_layout(set(), [_chain("_layout.html")], env) == []

    def test_empty_layout_chains(self) -> None:
        env = _env(
            {
                "_layout.html": "<html></html>",
                "page.html": '{% extends "_layout.html" %}',
            }
        )
        # No registered layouts → nothing to check against.
        assert check_page_extends_layout({"page.html"}, [], env) == []

    def test_kida_env_none(self) -> None:
        assert check_page_extends_layout({"page.html"}, [_chain("_layout.html")], None) == []

    def test_unloadable_template_is_skipped(self) -> None:
        env = _env({"_layout.html": "<html></html>"})
        # 'missing.html' isn't in the env loader → kida raises on get_template.
        issues = check_page_extends_layout({"missing.html"}, [_chain("_layout.html")], env)
        assert issues == []


class TestCompositionRuleIntegration:
    """The rule must run as part of ``app.check()``."""

    @pytest.mark.asyncio
    async def test_app_check_does_not_flag_oob_layout_chain_example(self, tmp_path) -> None:
        # Simulates the oob_layout_chain shape: page extends a kida partial that
        # is NOT in the layout chain. Should NOT trigger composition_extends.
        from chirp import App
        from chirp.config import AppConfig

        template_dir = tmp_path / "pages"
        template_dir.mkdir()
        (template_dir / "_layout.html").write_text(
            "<html><body>{% block content %}{% end %}</body></html>"
        )
        (template_dir / "_page_layout.html").write_text(
            "{% block content %}"
            "{% block page_root %}{% block page_content %}{% end %}{% end %}"
            "{% end %}"
        )
        (template_dir / "page.html").write_text(
            '{% extends "_page_layout.html" %}{% block page_content %}<p>hi</p>{% end %}'
        )

        app = App(config=AppConfig(template_dir=str(template_dir)))

        @app.route("/")
        def index():
            from chirp.templating.returns import Template

            return Template("page.html")

        from chirp.contracts import check_hypermedia_surface

        app._freeze()
        result = check_hypermedia_surface(app)
        ce_issues = [i for i in result.issues if i.category == "composition_extends"]
        assert ce_issues == []
