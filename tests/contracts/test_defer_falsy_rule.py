"""Suspense ``{% if key %}`` defer-falsy footgun contract rule.

Promotes the AGENTS.md / CLAUDE.md anti-pattern bullet ("``{% if key %}``
for Suspense deferred values: empty list, empty string, 0 — all falsy
after resolution") into a startup ``app.check()`` WARNING.
"""

import re

import pytest

from chirp.contracts.rules_defer_falsy import check_defer_falsy_conditionals
from chirp.contracts.types import Severity


class TestDeferFalsyRule:
    def test_template_without_defer_indicators_is_ignored(self) -> None:
        sources = {
            "page.html": ("<div>{% if items %}<p>{{ items|length }}</p>{% endif %}</div>"),
        }
        assert check_defer_falsy_conditionals(sources) == []

    def test_is_not_none_only_is_accepted(self) -> None:
        sources = {
            "page.html": (
                '{% if "stats" in __chirp_defer_pending__ %}'
                "<span>loading…</span>"
                "{% elif stats is not none %}"
                "<span>{{ stats.count }}</span>"
                "{% endif %}"
            ),
        }
        assert check_defer_falsy_conditionals(sources) == []

    def test_is_deferred_only_is_accepted(self) -> None:
        sources = {
            "page.html": (
                "{% if stats is deferred %}<span>loading…</span>"
                "{% else %}<span>{{ stats.count }}</span>{% endif %}"
            ),
        }
        assert check_defer_falsy_conditionals(sources) == []

    def test_bare_truthy_after_membership_check_is_flagged(self) -> None:
        sources = {
            "page.html": (
                '{% if "stats" in __chirp_defer_pending__ %}'
                "<span>loading…</span>"
                "{% elif stats %}"
                "<span>{{ stats.count }}</span>"
                "{% endif %}"
            ),
        }
        issues = check_defer_falsy_conditionals(sources)
        assert len(issues) == 1
        issue = issues[0]
        assert issue.severity == Severity.WARNING
        assert issue.category == "defer_falsy"
        assert issue.template == "page.html"
        assert "stats" in issue.message
        assert "is not none" in issue.message
        assert "__chirp_defer_pending__" in issue.message

    def test_bare_truthy_after_is_deferred_is_flagged(self) -> None:
        sources = {
            "page.html": (
                "{% if stats is deferred %}<span>loading…</span>"
                "{% endif %}"
                "<hr>"
                "{% if stats %}<span>{{ stats }}</span>{% endif %}"
            ),
        }
        issues = check_defer_falsy_conditionals(sources)
        assert len(issues) == 1
        assert issues[0].template == "page.html"

    def test_bare_not_truthy_is_flagged(self) -> None:
        sources = {
            "page.html": (
                '{% if "feed" in __chirp_defer_pending__ %}<span>loading…</span>'
                "{% endif %}"
                "{% if not feed %}<span>nothing yet</span>{% endif %}"
            ),
        }
        issues = check_defer_falsy_conditionals(sources)
        assert len(issues) == 1
        assert "feed" in issues[0].message

    def test_dedupes_repeated_bare_check_for_same_key(self) -> None:
        sources = {
            "page.html": (
                "{% if stats is deferred %}<span>loading…</span>{% endif %}"
                "{% if stats %}<a>1</a>{% endif %}"
                "{% if stats %}<a>2</a>{% endif %}"
                "{% if not stats %}<a>3</a>{% endif %}"
            ),
        }
        issues = check_defer_falsy_conditionals(sources)
        assert len(issues) == 1

    def test_multiple_bad_keys_each_flagged_once(self) -> None:
        sources = {
            "page.html": (
                '{% if "stats" in __chirp_defer_pending__ %}<a/>{% endif %}'
                '{% if "feed" in __chirp_defer_pending__ %}<a/>{% endif %}'
                "{% if stats %}<a/>{% endif %}"
                "{% if feed %}<a/>{% endif %}"
            ),
        }
        issues = check_defer_falsy_conditionals(sources)
        assert len(issues) == 2
        # Each issue mentions exactly one defer key in the "deferred key 'X'" phrase.
        flagged_keys: set[str] = set()
        for issue in issues:
            match = re.search(r"deferred key '([^']+)'", issue.message)
            assert match is not None, f"missing 'deferred key' phrase in: {issue.message}"
            flagged_keys.add(match.group(1))
        assert flagged_keys == {"stats", "feed"}

    def test_compound_expression_is_not_flagged(self) -> None:
        # Conservative v1: `{% if stats and other %}` is technically still
        # buggy but compound expressions are hard to disambiguate. Skip.
        sources = {
            "page.html": (
                "{% if stats is deferred %}<span>loading…</span>{% endif %}"
                "{% if stats and other %}<span>{{ stats }}</span>{% endif %}"
            ),
        }
        assert check_defer_falsy_conditionals(sources) == []

    def test_equality_is_not_flagged(self) -> None:
        sources = {
            "page.html": (
                "{% if stats is deferred %}<span>loading…</span>{% endif %}"
                "{% if stats == expected %}<span>match</span>{% endif %}"
            ),
        }
        assert check_defer_falsy_conditionals(sources) == []

    def test_whitespace_trimming_tags_are_handled(self) -> None:
        sources = {
            "page.html": (
                '{%- if "stats" in __chirp_defer_pending__ -%}<a/>{%- endif -%}'
                "{%- if stats -%}<a/>{%- endif -%}"
            ),
        }
        issues = check_defer_falsy_conditionals(sources)
        assert len(issues) == 1

    def test_substring_keys_are_not_confused(self) -> None:
        # `stats_count` shouldn't trigger when the defer key is `stats`.
        sources = {
            "page.html": (
                "{% if stats is deferred %}<span>loading…</span>{% endif %}"
                "{% if stats_count %}<span>n</span>{% endif %}"
            ),
        }
        assert check_defer_falsy_conditionals(sources) == []


class TestDeferFalsyRuleIntegration:
    """The rule must run as part of ``app.check()``."""

    @pytest.mark.asyncio
    async def test_app_check_flags_bare_if_in_template(self, tmp_path) -> None:
        from chirp import App
        from chirp.config import AppConfig

        template_dir = tmp_path / "templates"
        template_dir.mkdir()
        (template_dir / "page.html").write_text(
            "<html><body>"
            '{% if "stats" in __chirp_defer_pending__ %}'
            "<span>loading…</span>"
            "{% elif stats %}"
            "<span>{{ stats }}</span>"
            "{% endif %}"
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
        defer_issues = [i for i in result.issues if i.category == "defer_falsy"]
        assert len(defer_issues) == 1
        assert defer_issues[0].severity == Severity.WARNING
        assert "stats" in defer_issues[0].message
