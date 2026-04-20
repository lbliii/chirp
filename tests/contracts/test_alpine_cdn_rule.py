"""Bare jsDelivr Alpine CDN URL contract rule.

Promotes the existing ``tests/test_alpine.py`` regression check into a
startup contract: ``app.check()`` should refuse a bare jsDelivr URL
rather than letting it ship and silently break in the browser.
"""

import pytest

from chirp.contracts.rules_alpine_cdn import check_alpine_cdn_urls
from chirp.contracts.types import Severity


class TestAlpineCdnRule:
    def test_explicit_dist_path_is_accepted(self) -> None:
        sources = {
            "layout.html": (
                "<script defer "
                'src="https://cdn.jsdelivr.net/npm/alpinejs@3.15.8/dist/cdn.min.js"></script>'
            ),
        }
        assert check_alpine_cdn_urls(sources) == []

    def test_bare_alpine_core_url_is_flagged(self) -> None:
        sources = {
            "layout.html": (
                '<script defer src="https://cdn.jsdelivr.net/npm/alpinejs@3.15.8"></script>'
            ),
        }
        issues = check_alpine_cdn_urls(sources)
        assert len(issues) == 1
        issue = issues[0]
        assert issue.severity == Severity.ERROR
        assert issue.category == "alpine_cdn_url"
        assert issue.template == "layout.html"
        assert "alpinejs@3.15.8" in issue.message
        assert "/dist/cdn.min.js" in issue.message

    def test_bare_alpine_plugin_url_is_flagged(self) -> None:
        sources = {
            "layout.html": (
                '<script src="https://cdn.jsdelivr.net/npm/@alpinejs/focus@3.15.8"></script>'
            ),
        }
        issues = check_alpine_cdn_urls(sources)
        assert len(issues) == 1
        assert "@alpinejs/focus@3.15.8" in issues[0].message

    def test_non_alpine_jsdelivr_url_is_ignored(self) -> None:
        sources = {
            "layout.html": ('<script src="https://cdn.jsdelivr.net/npm/htmx.org@2.0.4"></script>'),
        }
        assert check_alpine_cdn_urls(sources) == []

    def test_explicit_csp_dist_path_is_accepted(self) -> None:
        sources = {
            "layout.html": (
                "<script defer "
                'src="https://cdn.jsdelivr.net/npm/@alpinejs/csp@3.15.8/dist/cdn.min.js">'
                "</script>"
            ),
        }
        assert check_alpine_cdn_urls(sources) == []

    def test_dedupes_repeated_bare_url_in_same_template(self) -> None:
        sources = {
            "layout.html": (
                '<script src="https://cdn.jsdelivr.net/npm/alpinejs@3.15.8"></script>'
                '<script src="https://cdn.jsdelivr.net/npm/alpinejs@3.15.8"></script>'
            ),
        }
        issues = check_alpine_cdn_urls(sources)
        assert len(issues) == 1

    def test_flags_each_bare_url_across_templates(self) -> None:
        sources = {
            "a.html": ('<script src="https://cdn.jsdelivr.net/npm/alpinejs@3.15.8"></script>'),
            "b.html": (
                '<script src="https://cdn.jsdelivr.net/npm/@alpinejs/mask@3.15.8"></script>'
            ),
        }
        issues = check_alpine_cdn_urls(sources)
        assert {i.template for i in issues} == {"a.html", "b.html"}


class TestAlpineCdnRuleIntegration:
    """The rule must run as part of ``app.check()``."""

    @pytest.mark.asyncio
    async def test_app_check_flags_bare_url_in_template(self, tmp_path) -> None:
        from chirp import App
        from chirp.config import AppConfig

        template_dir = tmp_path / "templates"
        template_dir.mkdir()
        (template_dir / "page.html").write_text(
            "<html><body>"
            '<script src="https://cdn.jsdelivr.net/npm/alpinejs@3.15.8"></script>'
            "<h1>Hi</h1>"
            "</body></html>"
        )
        app = App(config=AppConfig(template_dir=str(template_dir)))

        @app.route("/")
        def index():
            from chirp.templating.returns import Template

            return Template("page.html")

        from chirp.contracts import check_hypermedia_surface

        app._freeze()
        result = check_hypermedia_surface(app)
        alpine_issues = [i for i in result.issues if i.category == "alpine_cdn_url"]
        assert len(alpine_issues) == 1
        assert alpine_issues[0].severity == Severity.ERROR
