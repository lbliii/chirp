"""``suspense_defer`` contract rule.

Flags Suspense templates that self-declare a deferred key (via ``is deferred``
or ``__chirp_defer_pending__``) which no block depends on, so auto-discovery
finds nothing to re-render and the deferred data never reaches the DOM. The rule
recommends the ``defer_blocks=(...)`` escape hatch.
"""

import pytest
from kida import DictLoader, Environment

from chirp.contracts.rules_suspense_defer import check_suspense_undiscoverable
from chirp.contracts.types import Severity
from chirp.templating.suspense import DEFERRED


def _env(sources: dict[str, str]) -> Environment:
    """A kida env with Chirp's ``deferred`` test registered.

    Mirrors ``chirp.templating.integration`` line 177 so ``{% if x is
    deferred %}`` compiles and ``block_metadata()`` succeeds, exactly as it
    does inside ``app.check()``.
    """
    env = Environment(loader=DictLoader(sources))
    env.add_test("deferred", lambda val: val is DEFERRED)
    return env


class TestSuspenseDeferRule:
    def test_undiscoverable_key_is_flagged(self) -> None:
        # `stats` is declared deferred but lives outside any block, so no block's
        # depends_on references it: auto-discovery finds nothing.
        sources = {
            "page.html": (
                "<div>"
                "{% if stats is deferred %}<span>loading…</span>"
                "{% else %}<span>{{ stats.count }}</span>{% endif %}"
                "</div>"
            ),
        }
        issues = check_suspense_undiscoverable(sources, _env(sources))
        assert len(issues) == 1
        issue = issues[0]
        assert issue.severity == Severity.WARNING
        assert issue.category == "suspense_defer"
        assert issue.template == "page.html"
        assert "stats" in issue.message
        assert "defer_blocks" in issue.message

    def test_discoverable_key_is_not_flagged(self) -> None:
        # `stats` is referenced inside a block, so block_metadata().depends_on
        # for `stats_card` includes `stats` — auto-discovery succeeds.
        sources = {
            "page.html": (
                "{% block stats_card %}"
                "{% if stats is deferred %}<span>loading…</span>"
                "{% else %}<span>{{ stats.count }}</span>{% endif %}"
                "{% endblock %}"
            ),
        }
        assert check_suspense_undiscoverable(sources, _env(sources)) == []

    def test_membership_declaration_discoverable_is_not_flagged(self) -> None:
        sources = {
            "page.html": (
                "{% block feed_panel %}"
                '{% if "feed" in __chirp_defer_pending__ %}<span>loading…</span>'
                "{% else %}<ul>{% for x in feed %}<li>{{ x }}</li>{% endfor %}</ul>"
                "{% endif %}"
                "{% endblock %}"
            ),
        }
        assert check_suspense_undiscoverable(sources, _env(sources)) == []

    def test_sync_only_template_is_not_flagged(self) -> None:
        # No defer self-declaration at all → never a Suspense target for this rule.
        sources = {
            "page.html": (
                "{% block body %}{% if items %}<p>{{ items|length }}</p>{% endif %}{% endblock %}"
            ),
        }
        assert check_suspense_undiscoverable(sources, _env(sources)) == []

    def test_defer_blocks_equipped_template_is_not_flagged(self) -> None:
        # The key is undiscoverable (outside any block) but the route handler
        # opts out via defer_blocks=, so the rule must stay silent.
        sources = {
            "page.html": (
                "<div>"
                "{% if stats is deferred %}<span>loading…</span>"
                "{% else %}<span>{{ stats.count }}</span>{% endif %}"
                "</div>"
            ),
        }
        issues = check_suspense_undiscoverable(
            sources,
            _env(sources),
            defer_blocks_templates=frozenset({"page.html"}),
        )
        assert issues == []

    def test_chirpui_templates_are_skipped(self) -> None:
        sources = {
            "chirpui/widget.html": "{% if stats is deferred %}<span>x</span>{% endif %}",
            "chirp/internal.html": "{% if stats is deferred %}<span>x</span>{% endif %}",
        }
        assert check_suspense_undiscoverable(sources, _env(sources)) == []

    def test_none_env_returns_empty(self) -> None:
        sources = {"page.html": "{% if stats is deferred %}x{% endif %}"}
        assert check_suspense_undiscoverable(sources, None) == []

    def test_multiple_undiscoverable_keys_each_flagged_once(self) -> None:
        sources = {
            "page.html": (
                "{% if stats is deferred %}<a/>{% endif %}"
                '{% if "feed" in __chirp_defer_pending__ %}<a/>{% endif %}'
            ),
        }
        issues = check_suspense_undiscoverable(sources, _env(sources))
        assert len(issues) == 2
        flagged = {i.template for i in issues}
        assert flagged == {"page.html"}
        keys = sorted(next(k for k in ("stats", "feed") if k in i.message) for i in issues)
        assert keys == ["feed", "stats"]

    def test_mixed_discoverable_and_undiscoverable(self) -> None:
        # `stats` is inside a block (discoverable); `feed` is outside (not).
        sources = {
            "page.html": (
                "{% block stats_card %}"
                "{% if stats is deferred %}<span>loading…</span>"
                "{% else %}{{ stats.count }}{% endif %}"
                "{% endblock %}"
                "<div>{% if feed is deferred %}<span>loading…</span>"
                "{% else %}{{ feed }}{% endif %}</div>"
            ),
        }
        issues = check_suspense_undiscoverable(sources, _env(sources))
        assert len(issues) == 1
        assert "feed" in issues[0].message
        assert "stats" not in issues[0].message


class TestSuspenseDeferRuleIntegration:
    """The rule must run as part of ``app.check()`` and honor severity override."""

    @pytest.mark.asyncio
    async def test_app_check_flags_undiscoverable_key(self, tmp_path) -> None:
        from chirp import App
        from chirp.config import AppConfig

        template_dir = tmp_path / "templates"
        template_dir.mkdir()
        # `stats` declared deferred but outside any block → undiscoverable.
        (template_dir / "page.html").write_text(
            "<html><body>"
            "{% if stats is deferred %}<span>loading…</span>"
            "{% else %}<span>{{ stats }}</span>{% endif %}"
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
        issues = [i for i in result.issues if i.category == "suspense_defer"]
        assert len(issues) == 1
        assert issues[0].severity == Severity.WARNING
        assert "stats" in issues[0].message

    @pytest.mark.asyncio
    async def test_app_check_clean_when_block_depends_on_key(self, tmp_path) -> None:
        from chirp import App
        from chirp.config import AppConfig

        template_dir = tmp_path / "templates"
        template_dir.mkdir()
        (template_dir / "page.html").write_text(
            "<html><body>"
            "{% block stats_card %}"
            "{% if stats is deferred %}<span>loading…</span>"
            "{% else %}<span>{{ stats }}</span>{% endif %}"
            "{% endblock %}"
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
        issues = [i for i in result.issues if i.category == "suspense_defer"]
        assert issues == []

    @pytest.mark.asyncio
    async def test_app_check_exempts_defer_blocks_handler(self, tmp_path) -> None:
        from chirp import App
        from chirp.config import AppConfig

        template_dir = tmp_path / "templates"
        template_dir.mkdir()
        # `stats` is declared deferred OUTSIDE any block, so it is genuinely
        # undiscoverable — identical to the template in
        # ``test_app_check_flags_undiscoverable_key`` (which gets 1 issue). The
        # ONLY thing that suppresses the warning here is the handler's
        # ``defer_blocks=`` opt-out, so this test is load-bearing for the
        # exemption (it would fail if ``_collect_defer_blocks_templates`` broke).
        (template_dir / "page.html").write_text(
            "<html><body>"
            "{% if stats is deferred %}<span>loading…</span>"
            "{% else %}<span>{{ stats }}</span>{% endif %}"
            "</body></html>"
        )
        app = App(config=AppConfig(template_dir=str(template_dir)))

        @app.route("/")
        def index():
            from chirp.templating.returns import Suspense

            async def _load():
                return {"x": 1}

            return Suspense(
                "page.html",
                defer_blocks=("stats",),
                stats=_load(),
            )

        from chirp.contracts import check_hypermedia_surface

        app._freeze()
        result = check_hypermedia_surface(app)
        issues = [i for i in result.issues if i.category == "suspense_defer"]
        assert issues == []

    @pytest.mark.asyncio
    async def test_severity_override_to_error(self, tmp_path) -> None:
        from chirp import App
        from chirp.config import AppConfig

        template_dir = tmp_path / "templates"
        template_dir.mkdir()
        (template_dir / "page.html").write_text(
            "<html><body>"
            "{% if stats is deferred %}<span>loading…</span>"
            "{% else %}<span>{{ stats }}</span>{% endif %}"
            "</body></html>"
        )
        app = App(config=AppConfig(template_dir=str(template_dir)))
        app.override_contract_severity("suspense_defer", Severity.ERROR)

        @app.route("/")
        def index():
            from chirp.templating.returns import Template

            return Template("page.html")

        from chirp.contracts import check_hypermedia_surface

        app._freeze()
        result = check_hypermedia_surface(app)
        issues = [i for i in result.issues if i.category == "suspense_defer"]
        assert len(issues) == 1
        assert issues[0].severity == Severity.ERROR


# Module-level handlers so inspect.getsource() can read their bodies, exercising
# the handler-source scan in _collect_defer_blocks_templates directly.
def _handler_with_defer_blocks():
    from chirp.templating.returns import Suspense

    return Suspense("dash.html", defer_blocks=("stats",), stats=None)


def _handler_without_defer_blocks():
    from chirp.templating.returns import Suspense

    return Suspense("plain.html", stats=None)


class _Route:
    def __init__(self, handler) -> None:
        self.handler = handler
        self.page_source_handler = None


class _Router:
    def __init__(self, *handlers) -> None:
        self.routes = [_Route(h) for h in handlers]


class TestCollectDeferBlocksTemplates:
    """Direct coverage of the defer_blocks= handler-source exemption scan."""

    def test_handler_with_defer_blocks_is_exempt(self) -> None:
        from chirp.contracts.checker import _collect_defer_blocks_templates

        exempt = _collect_defer_blocks_templates(
            _Router(_handler_with_defer_blocks, _handler_without_defer_blocks)
        )
        # Only the template rendered by a defer_blocks= handler is exempt.
        assert "dash.html" in exempt
        assert "plain.html" not in exempt

    def test_no_handlers_is_empty(self) -> None:
        from chirp.contracts.checker import _collect_defer_blocks_templates

        assert _collect_defer_blocks_templates(_Router()) == frozenset()
