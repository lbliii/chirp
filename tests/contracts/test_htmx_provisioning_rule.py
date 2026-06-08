"""Page-level htmx provisioning contract rule (#185).

htmx attributes are inert without the htmx runtime. ``app.check()`` should
ERROR when an app template emits ``hx-*`` / ``sse-*`` but htmx is provisioned
via neither ``AppConfig(htmx=True)`` (Mode A) nor an explicit htmx ``<script>``
in the layout / extends chain (Mode B).
"""

import pytest

from chirp.contracts.rules_htmx_provisioning import check_htmx_provisioning
from chirp.contracts.types import Severity


class _Config:
    """Minimal stand-in for AppConfig with a controllable htmx flag."""

    def __init__(self, htmx: bool = False) -> None:
        self.htmx = htmx


_HTMX_SCRIPT = '<script src="https://unpkg.com/htmx.org@2.0.4"></script>'
_HTMX_SSE_SCRIPT = '<script src="https://unpkg.com/htmx-ext-sse@2.2.2/sse.js"></script>'


class TestHtmxProvisioningRule:
    def test_hx_post_without_provisioning_is_flagged(self) -> None:
        sources = {"page.html": '<form hx-post="/save"><button>Save</button></form>'}
        issues = check_htmx_provisioning(sources, _Config(htmx=False))
        assert len(issues) == 1
        issue = issues[0]
        assert issue.severity == Severity.ERROR
        assert issue.category == "htmx_provisioning"
        assert issue.template == "page.html"
        assert "AppConfig(htmx=True)" in issue.message
        assert "<script" in issue.message

    def test_script_in_extended_layout_provisions_mode_b(self) -> None:
        # page.html extends base.html, which ships the htmx script. The
        # extends closure reaches base.html so the page is provisioned.
        sources = {
            "base.html": f"<head>{_HTMX_SCRIPT}</head>{{% block content %}}{{% end %}}",
            "page.html": (
                '{% extends "base.html" %}{% block content %}<form hx-post="/save"></form>{% end %}'
            ),
        }
        assert check_htmx_provisioning(sources, _Config(htmx=False)) == []

    def test_script_in_unreachable_template_does_not_provision(self) -> None:
        # An htmx script sitting in a template the offender never reaches (a
        # bundled framework shell the app does not extend) must NOT count.
        sources = {
            "chirp/layouts/shell.html": f"<head>{_HTMX_SCRIPT}</head>",
            "page.html": '<form hx-post="/save"></form>',
        }
        issues = check_htmx_provisioning(sources, _Config(htmx=False))
        assert len(issues) == 1
        assert issues[0].template == "page.html"

    def test_script_reachable_via_layout_chain_provisions(self) -> None:
        # Filesystem-routing: page.html has no extends but is composed into a
        # layout chain whose layout reaches a shell shipping the htmx script.
        sources = {
            "chirp/layouts/shell.html": f"<head>{_HTMX_SCRIPT}</head>",
            "_layout.html": '{% extends "chirp/layouts/shell.html" %}',
            "page.html": '<form hx-post="/save"></form>',
        }

        class _Layout:
            template_name = "_layout.html"

        class _Chain:
            layouts = (_Layout(),)

        assert (
            check_htmx_provisioning(
                sources,
                _Config(htmx=False),
                layout_chains=(_Chain(),),
                page_leaf_templates=("page.html",),
            )
            == []
        )

    def test_config_htmx_true_provisions_mode_a(self) -> None:
        sources = {"page.html": '<form hx-post="/save"></form>'}
        assert check_htmx_provisioning(sources, _Config(htmx=True)) == []

    def test_sse_attributes_without_provisioning_are_flagged(self) -> None:
        sources = {
            "feed.html": (
                '<div hx-ext="sse" sse-connect="/events"><div sse-swap="tick">...</div></div>'
            )
        }
        issues = check_htmx_provisioning(sources, _Config(htmx=False))
        assert len(issues) == 1
        assert issues[0].category == "htmx_provisioning"
        assert issues[0].template == "feed.html"

    def test_framework_template_usage_is_not_app_responsibility(self) -> None:
        # hx-* ONLY inside chirp/, chirpui/, or chirp_docs/ templates -> no app
        # issue (the developer cannot edit framework-shipped templates; the host
        # page provisions htmx).
        sources = {
            "chirp/layouts/shell.html": '<form hx-post="/x"></form>',
            "chirpui/widget.html": '<div hx-get="/y"></div>',
            "chirp_docs/doc_list.html": '<input hx-get="/docs/search" hx-trigger="keyup">',
            "page.html": "<h1>Hello</h1>",
        }
        assert check_htmx_provisioning(sources, _Config(htmx=False)) == []

    def test_no_htmx_usage_is_clean(self) -> None:
        # Plain scaffold case: no hx-*/sse-* anywhere -> clean regardless of
        # provisioning.
        sources = {"page.html": "<h1>Static page</h1><a href='/about'>About</a>"}
        assert check_htmx_provisioning(sources, _Config(htmx=False)) == []

    def test_dedupes_multiple_attrs_in_same_template(self) -> None:
        sources = {
            "page.html": (
                '<form hx-post="/save" hx-target="#out" hx-trigger="submit"></form>'
                '<a hx-get="/more">More</a>'
            )
        }
        issues = check_htmx_provisioning(sources, _Config(htmx=False))
        assert len(issues) == 1

    def test_flags_each_template_across_sources(self) -> None:
        sources = {
            "a.html": '<a hx-get="/a">A</a>',
            "b.html": '<form hx-post="/b"></form>',
        }
        issues = check_htmx_provisioning(sources, _Config(htmx=False))
        assert {i.template for i in issues} == {"a.html", "b.html"}

    def test_sse_extension_script_alone_provisions(self) -> None:
        # htmx-ext-sse@2.2.2/sse.js src contains 'htmx' -> Mode B satisfied.
        sources = {
            "base.html": f"<head>{_HTMX_SSE_SCRIPT}</head>{{% block content %}}{{% end %}}",
            "feed.html": (
                '{% extends "base.html" %}'
                '{% block content %}<div hx-ext="sse" sse-connect="/events"></div>{% end %}'
            ),
        }
        assert check_htmx_provisioning(sources, _Config(htmx=False)) == []

    def test_self_hosted_htmx_script_provisions(self) -> None:
        sources = {
            "base.html": '<script src="/static/htmx.min.js"></script>{% block c %}{% end %}',
            "page.html": '{% extends "base.html" %}{% block c %}<form hx-post="/save"></form>{% end %}',
        }
        assert check_htmx_provisioning(sources, _Config(htmx=False)) == []

    def test_jsdelivr_htmx_script_provisions(self) -> None:
        sources = {
            "base.html": (
                '<script src="https://cdn.jsdelivr.net/npm/htmx.org@2.0.4"></script>'
                "{% block c %}{% end %}"
            ),
            "page.html": '{% extends "base.html" %}{% block c %}<form hx-post="/save"></form>{% end %}',
        }
        assert check_htmx_provisioning(sources, _Config(htmx=False)) == []

    def test_script_in_same_template_provisions(self) -> None:
        # Standalone-example shape: the htmx script and hx-* live in the same
        # template (the offender is its own seed).
        sources = {
            "search.html": (
                f"<html><head>{_HTMX_SCRIPT}</head>"
                '<body><input hx-get="/search" hx-trigger="keyup"></body></html>'
            )
        }
        assert check_htmx_provisioning(sources, _Config(htmx=False)) == []

    def test_bare_hx_swap_oob_is_not_a_usage_trigger(self) -> None:
        # hx-swap-oob / hx-disinherit appear in OOB / deferred fragments and are
        # not standalone provisioning triggers.
        sources = {"frag.html": '<div hx-swap-oob="true" hx-disinherit="*">x</div>'}
        assert check_htmx_provisioning(sources, _Config(htmx=False)) == []

    def test_sibling_page_script_does_not_suppress_other_offender(self) -> None:
        # #185 false-negative regression: page A is a standalone full page that
        # ships its OWN htmx <script> and uses hx-*. Sibling full page B uses
        # hx-* but has no script in ITS OWN closure. A naive app-global union
        # over all seeds would find A's script and wrongly clear B. Per-page
        # semantics must still ERROR on B while leaving A clean.
        sources = {
            "a.html": (
                f'<html><head>{_HTMX_SCRIPT}</head><body><form hx-post="/a"></form></body></html>'
            ),
            "b.html": '<form hx-post="/b"><button>Save</button></form>',
        }
        issues = check_htmx_provisioning(
            sources,
            _Config(htmx=False),
            page_leaf_templates=("a.html", "b.html"),
            full_page_templates=("a.html", "b.html"),
        )
        assert [i.template for i in issues] == ["b.html"]
        assert issues[0].severity == Severity.ERROR
        assert issues[0].category == "htmx_provisioning"

    def test_sibling_page_script_does_not_suppress_other_offender_strict_default(
        self,
    ) -> None:
        # Same regression but exercising the strict default branch (no
        # full_page_templates passed -> every offender treated as a full page).
        sources = {
            "a.html": (
                f'<html><head>{_HTMX_SCRIPT}</head><body><form hx-post="/a"></form></body></html>'
            ),
            "b.html": '<form hx-post="/b"><button>Save</button></form>',
        }
        issues = check_htmx_provisioning(sources, _Config(htmx=False))
        assert [i.template for i in issues] == ["b.html"]

    def test_fragment_only_template_is_not_flagged(self) -> None:
        # A fragment-only template (returned via Fragment/ValidationError/OOB,
        # never a full Template/Page) swaps into an already-provisioned host
        # page. It uses hx-* but is NOT a full page, so it must not be flagged on
        # its own — the host page owns provisioning. This is the kanban/islands
        # example shape (board.html is the provisioned page; the inline edit
        # fragment is swapped into it).
        sources = {
            "board.html": (
                f"<html><head>{_HTMX_SCRIPT}</head>"
                '<body><div hx-get="/refresh"></div></body></html>'
            ),
            "task_form.html": '<form hx-post="/task"><button>Save</button></form>',
        }
        issues = check_htmx_provisioning(
            sources,
            _Config(htmx=False),
            # board.html is a full page; task_form.html is fragment-only (absent).
            full_page_templates=("board.html",),
        )
        assert issues == []

    def test_fragment_only_template_flagged_when_host_page_unprovisioned(self) -> None:
        # The host obligation is real: if the only full page that exists is
        # itself unprovisioned, that full page is flagged. The fragment is still
        # not flagged (host owns it) — but the app does not silently pass.
        sources = {
            "board.html": '<html><body><div hx-get="/refresh"></div></body></html>',
            "task_form.html": '<form hx-post="/task"></form>',
        }
        issues = check_htmx_provisioning(
            sources,
            _Config(htmx=False),
            full_page_templates=("board.html",),
        )
        assert [i.template for i in issues] == ["board.html"]

    def test_component_imported_by_provisioned_page_is_clean(self) -> None:
        # A component pulled into a provisioned page via {% from ... import %}
        # is reachable in that page's forward closure, so the page (and its
        # imports) are provisioned. The component itself is fragment-only here.
        sources = {
            "board.html": (
                f"<html><head>{_HTMX_SCRIPT}</head><body>"
                '{% from "_card.html" import card %}{{ card() }}'
                "</body></html>"
            ),
            "_card.html": ('{% macro card() %}<div hx-get="/card"></div>{% end %}'),
        }
        issues = check_htmx_provisioning(
            sources,
            _Config(htmx=False),
            full_page_templates=("board.html",),
        )
        assert issues == []

    def test_different_layout_with_script_does_not_suppress_other_page_chain(self) -> None:
        # #185 LAYOUT-LEVEL false-negative regression. Section A is composed by
        # layout_a.html (ships an htmx <script>); section B is composed by a
        # DIFFERENT, script-LESS layout_b.html. A prior global UNION of every
        # discovered layout wrongly cleared B because A's layout script was in
        # the union. Per-composing-chain seeding must still ERROR on B while
        # leaving A clean.
        sources = {
            "layout_a.html": f"<head>{_HTMX_SCRIPT}</head>{{% block content %}}{{% end %}}",
            "layout_b.html": "<head></head>{% block content %}{% end %}",
            "a.html": '<form hx-post="/a"></form>',
            "b.html": '<form hx-post="/b"></form>',
        }

        class _Layout:
            def __init__(self, name: str) -> None:
                self.template_name = name

        class _Chain:
            def __init__(self, layout_name: str) -> None:
                self.layouts = (_Layout(layout_name),)

        chain_a = _Chain("layout_a.html")
        chain_b = _Chain("layout_b.html")

        issues = check_htmx_provisioning(
            sources,
            _Config(htmx=False),
            # Both chains are discovered app-wide (the union would see both).
            layout_chains=(chain_a, chain_b),
            # But each leaf is composed by exactly ONE of them.
            layout_chains_by_leaf={"a.html": chain_a, "b.html": chain_b},
            page_leaf_templates=("a.html", "b.html"),
            full_page_templates=("a.html", "b.html"),
        )
        assert [i.template for i in issues] == ["b.html"]
        assert issues[0].severity == Severity.ERROR
        assert issues[0].category == "htmx_provisioning"

    def test_leaf_reused_across_chains_unions_composing_layouts(self) -> None:
        # The same leaf template mounted at two paths is composed by two chains;
        # an htmx script in EITHER composing layout provisions the leaf.
        sources = {
            "layout_plain.html": "<head></head>{% block content %}{% end %}",
            "layout_htmx.html": f"<head>{_HTMX_SCRIPT}</head>{{% block content %}}{{% end %}}",
            "page.html": '<form hx-post="/save"></form>',
        }

        class _Layout:
            def __init__(self, name: str) -> None:
                self.template_name = name

        class _Chain:
            def __init__(self, layout_name: str) -> None:
                self.layouts = (_Layout(layout_name),)

        issues = check_htmx_provisioning(
            sources,
            _Config(htmx=False),
            layout_chains_by_leaf={
                # checker accumulates multiple composing chains per leaf as a list
                "page.html": [_Chain("layout_plain.html"), _Chain("layout_htmx.html")],
            },
            page_leaf_templates=("page.html",),
            full_page_templates=("page.html",),
        )
        assert issues == []

    def test_decorator_route_offender_without_chain_self_provisions(self) -> None:
        # With per-leaf seeding active, a decorator-route / standalone Template
        # offender (no entry in layout_chains_by_leaf) is seeded only with
        # itself — so it must ship its own script. Page A here has a layout chain
        # with a script; standalone page B is unrelated and still ERRORs.
        sources = {
            "layout_a.html": f"<head>{_HTMX_SCRIPT}</head>{{% block content %}}{{% end %}}",
            "a.html": '<form hx-post="/a"></form>',
            "standalone.html": '<form hx-post="/b"></form>',
        }

        class _Layout:
            template_name = "layout_a.html"

        class _Chain:
            layouts = (_Layout(),)

        chain_a = _Chain()
        issues = check_htmx_provisioning(
            sources,
            _Config(htmx=False),
            layout_chains=(chain_a,),
            layout_chains_by_leaf={"a.html": chain_a},
            page_leaf_templates=("a.html",),
            full_page_templates=("a.html", "standalone.html"),
        )
        assert [i.template for i in issues] == ["standalone.html"]

    def test_shared_layout_script_provisions_all_offenders(self) -> None:
        # The flip side: a script in a SHARED layout (composed into both pages)
        # provisions every offender that the layout chain composes.
        sources = {
            "_layout.html": f"<head>{_HTMX_SCRIPT}</head>{{% block content %}}{{% end %}}",
            "a.html": '<form hx-post="/a"></form>',
            "b.html": '<form hx-post="/b"></form>',
        }

        class _Layout:
            template_name = "_layout.html"

        class _Chain:
            layouts = (_Layout(),)

        assert (
            check_htmx_provisioning(
                sources,
                _Config(htmx=False),
                layout_chains=(_Chain(),),
                page_leaf_templates=("a.html", "b.html"),
            )
            == []
        )

    def test_missing_htmx_attr_on_config_defaults_to_unprovisioned(self) -> None:
        # An older config object without an htmx attribute must not crash and
        # must behave as not-provisioned (getattr default False).
        class _NoFlag:
            pass

        sources = {"page.html": '<form hx-post="/save"></form>'}
        issues = check_htmx_provisioning(sources, _NoFlag())
        assert len(issues) == 1
        assert issues[0].category == "htmx_provisioning"


class TestHtmxProvisioningRuleIntegration:
    """The rule must run as part of ``app.check()`` against a real App."""

    @pytest.mark.asyncio
    async def test_app_check_flags_unprovisioned_htmx(self, tmp_path) -> None:
        from chirp import App
        from chirp.config import AppConfig
        from chirp.contracts import check_hypermedia_surface
        from chirp.templating.returns import Template

        template_dir = tmp_path / "templates"
        template_dir.mkdir()
        (template_dir / "page.html").write_text(
            '<html><body><form hx-post="/save"><button>Save</button></form></body></html>'
        )
        app = App(config=AppConfig(template_dir=str(template_dir)))

        @app.route("/")
        def index():
            return Template("page.html")

        @app.route("/save", methods=["POST"])
        def save(request):
            return Template("page.html")

        app._freeze()
        result = check_hypermedia_surface(app)
        issues = [i for i in result.issues if i.category == "htmx_provisioning"]
        assert len(issues) == 1
        assert issues[0].severity == Severity.ERROR
        assert issues[0].template == "page.html"

    @pytest.mark.asyncio
    async def test_app_check_passes_with_config_htmx(self, tmp_path) -> None:
        from chirp import App
        from chirp.config import AppConfig
        from chirp.contracts import check_hypermedia_surface
        from chirp.templating.returns import Template

        template_dir = tmp_path / "templates"
        template_dir.mkdir()
        (template_dir / "page.html").write_text(
            "<html><body><form hx-post='/save'></form></body></html>"
        )
        app = App(config=AppConfig(template_dir=str(template_dir), htmx=True))

        @app.route("/")
        def index():
            return Template("page.html")

        @app.route("/save", methods=["POST"])
        def save(request):
            return Template("page.html")

        app._freeze()
        result = check_hypermedia_surface(app)
        assert [i for i in result.issues if i.category == "htmx_provisioning"] == []

    @pytest.mark.asyncio
    async def test_app_check_passes_with_layout_script(self, tmp_path) -> None:
        from chirp import App
        from chirp.config import AppConfig
        from chirp.contracts import check_hypermedia_surface
        from chirp.templating.returns import Template

        template_dir = tmp_path / "templates"
        template_dir.mkdir()
        (template_dir / "base.html").write_text(
            "<html><head>"
            '<script src="https://unpkg.com/htmx.org@2.0.4"></script>'
            "</head><body>{% block content %}{% end %}</body></html>"
        )
        (template_dir / "page.html").write_text(
            "{% extends \"base.html\" %}{% block content %}<form hx-post='/save'></form>{% end %}"
        )
        app = App(config=AppConfig(template_dir=str(template_dir)))

        @app.route("/")
        def index():
            return Template("page.html")

        @app.route("/save", methods=["POST"])
        def save(request):
            return Template("page.html")

        app._freeze()
        result = check_hypermedia_surface(app)
        assert [i for i in result.issues if i.category == "htmx_provisioning"] == []

    @pytest.mark.asyncio
    async def test_app_check_layout_script_in_one_section_does_not_clear_other(
        self, tmp_path
    ) -> None:
        # End-to-end #185 LAYOUT-LEVEL regression through real filesystem pages.
        # Section a/ is composed by a/_layout.html which ships an htmx <script>;
        # section b/ is composed by a DIFFERENT, script-less b/_layout.html. The
        # shared root _layout.html ships no script. Only b/page.html must ERROR;
        # a/page.html stays clean. A global layout union would wrongly clear b.
        from chirp import App
        from chirp.config import AppConfig
        from chirp.contracts import check_hypermedia_surface

        pages_dir = tmp_path / "pages"
        (pages_dir / "a").mkdir(parents=True)
        (pages_dir / "b").mkdir(parents=True)
        # Shared root layout — no htmx script.
        (pages_dir / "_layout.html").write_text(
            "<html><body>{% block content %}{% end %}</body></html>"
        )
        # Section A layout ships the htmx script.
        (pages_dir / "a" / "_layout.html").write_text(
            f"<head>{_HTMX_SCRIPT}</head>"
            '<div id="app-content">{% block content %}{% end %}</div>'
        )
        (pages_dir / "a" / "page.py").write_text("def get(): return {}")
        (pages_dir / "a" / "page.html").write_text('<form hx-get="/a"><button>Go</button></form>')
        # Section B layout has NO htmx script.
        (pages_dir / "b" / "_layout.html").write_text(
            '<div id="app-content">{% block content %}{% end %}</div>'
        )
        (pages_dir / "b" / "page.py").write_text("def get(): return {}")
        (pages_dir / "b" / "page.html").write_text('<form hx-get="/b"><button>Go</button></form>')

        app = App(config=AppConfig(template_dir=str(pages_dir)))
        app.mount_pages(str(pages_dir))
        app._freeze()
        result = check_hypermedia_surface(app)
        issues = [i for i in result.issues if i.category == "htmx_provisioning"]
        assert [i.template for i in issues] == ["b/page.html"]
        assert issues[0].severity == Severity.ERROR
