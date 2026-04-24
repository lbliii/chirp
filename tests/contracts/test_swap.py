"""Tests for swap safety — broad hx-target + mutating requests."""

from chirp.contracts import Severity
from chirp.contracts.rules_swap import check_swap_safety, check_view_transition_safety


class TestSwapSafetyWarnings:
    """Warnings for broad inherited hx-target plus mutating requests."""

    def test_warns_for_mutation_without_local_target(self):
        template_sources = {
            "_layout.html": (
                '<body hx-boost="true" hx-target="#app-content">'
                "<main>{% block content %}{% endblock %}</main>"
                "</body>"
            ),
            "docs.html": '<form hx-post="/docs/new"><button>Save</button></form>',
        }
        issues = check_swap_safety(template_sources)
        assert len(issues) == 1
        assert issues[0].severity == Severity.WARNING
        assert issues[0].category == "swap_safety"
        assert "Action()" in issues[0].message

    def test_no_warning_when_mutation_has_local_target(self):
        template_sources = {
            "_layout.html": '<body hx-boost="true" hx-target="#app-content"></body>',
            "docs.html": (
                '<form hx-post="/docs/new" hx-target="#editor"><button>Save</button></form>'
            ),
        }
        issues = check_swap_safety(template_sources)
        assert issues == []

    def test_no_warning_when_swap_none(self):
        template_sources = {
            "_layout.html": '<body hx-boost="true" hx-target="#app-content"></body>',
            "docs.html": '<form hx-post="/docs/new" hx-swap="none"></form>',
        }
        issues = check_swap_safety(template_sources)
        assert issues == []

    def test_no_warning_for_form_action_get_or_omitted(self):
        """Form with action and method=get or omitted (HTML default) is not mutating."""
        template_sources = {
            "_layout.html": '<body hx-boost="true" hx-target="#app-content"></body>',
            "search.html": '<form action="/search"></form>',
        }
        issues = check_swap_safety(template_sources)
        assert issues == []

    def test_warns_for_form_action_post_without_target(self):
        """Form with action method=post and no hx-target inherits broad target."""
        template_sources = {
            "_layout.html": '<body hx-boost="true" hx-target="#app-content"></body>',
            "login.html": '<form action="/login" method="post"><button>Submit</button></form>',
        }
        issues = check_swap_safety(template_sources)
        assert len(issues) == 1
        assert issues[0].category == "swap_safety"

    def test_relative_extends_chain_scopes_select_inheritance(self):
        """Relative extends should still find inherited broad hx-select scopes."""
        template_sources = {
            "_layouts/base.html": (
                '<main hx-boost="true" hx-select="#page-content">'
                "{% block content %}{% endblock %}"
                "</main>"
            ),
            "pages/edit.html": (
                '{% extends "../_layouts/base.html" %}'
                "{% block content %}"
                '<form hx-post="/save"><button>Save</button></form>'
                "{% endblock %}"
            ),
        }

        issues = check_swap_safety(template_sources)

        assert len(issues) == 1
        assert issues[0].category == "select_inheritance"
        assert '"#page-content" (_layouts/base.html)' in (issues[0].details or "")

    def test_alias_extends_chain_scopes_select_inheritance(self):
        """Alias extends should use the configured Kida alias map for swap checks."""
        template_sources = {
            "_layouts/base.html": (
                '<main hx-boost="true" hx-select="#page-content">'
                "{% block content %}{% endblock %}"
                "</main>"
            ),
            "pages/edit.html": (
                '{% extends "@layouts/base.html" %}'
                "{% block content %}"
                '<form hx-post="/save"><button>Save</button></form>'
                "{% endblock %}"
            ),
        }

        issues = check_swap_safety(template_sources, template_aliases={"layouts": "_layouts"})

        assert len(issues) == 1
        assert issues[0].category == "select_inheritance"
        assert '"#page-content" (_layouts/base.html)' in (issues[0].details or "")

    def test_warns_for_sse_swap_without_local_target(self):
        template_sources = {
            "_layout.html": '<body hx-boost="true" hx-target="#app-content"></body>',
            "chat.html": (
                '<div hx-ext="sse" sse-connect="/chat/events">'
                '<span sse-swap="fragment" hx-swap="beforeend"></span>'
                "</div>"
            ),
        }
        issues = check_swap_safety(template_sources)
        assert len(issues) == 1
        assert issues[0].severity == Severity.WARNING
        assert issues[0].category == "swap_safety"
        assert "SSE swap element has no explicit hx-target" in issues[0].message

    def test_no_warning_for_sse_swap_with_local_target(self):
        template_sources = {
            "_layout.html": '<body hx-boost="true" hx-target="#app-content"></body>',
            "chat.html": (
                '<div hx-ext="sse" sse-connect="/chat/events">'
                '<span sse-swap="fragment" hx-swap="beforeend" hx-target="this"></span>'
                "</div>"
            ),
        }
        issues = check_swap_safety(template_sources)
        assert issues == []

    def test_no_warning_for_sse_swap_when_connect_has_disinherit(self):
        """sse-connect with hx-disinherit skips WARNING; INFO suggests hx-target."""
        template_sources = {
            "_layout.html": '<body hx-boost="true" hx-target="#main"></body>',
            "ask.html": (
                '<article hx-ext="sse" sse-connect="{{ stream_url }}" '
                'hx-disinherit="hx-target hx-swap">'
                '<div class="answer" sse-swap="answer">...</div>'
                "</article>"
            ),
        }
        issues = check_swap_safety(template_sources)
        assert len(issues) == 1
        assert issues[0].severity == Severity.INFO
        assert "hx-target" in issues[0].message

    def test_no_info_when_sse_swap_has_hx_target_this(self):
        """sse-swap with hx-target='this' gets no INFO suggestion."""
        template_sources = {
            "_layout.html": '<body hx-boost="true" hx-target="#main"></body>',
            "ask.html": (
                '<article hx-ext="sse" sse-connect="{{ stream_url }}" '
                'hx-disinherit="hx-target hx-swap">'
                '<div class="answer" sse-swap="answer" hx-target="this">...</div>'
                "</article>"
            ),
        }
        issues = check_swap_safety(template_sources)
        assert issues == []


class TestViewTransitionSafetyWarnings:
    """Warnings for broad View Transition scopes with OOB/SSE updates."""

    def test_warns_for_transition_true_on_broad_live_container(self):
        template_sources = {
            "_layout.html": (
                '<main id="main" hx-boost="true" hx-target="#main" '
                'hx-swap="innerHTML transition:true">'
                "{% block content %}{% endblock %}"
                "</main>"
            ),
            "events.html": (
                '<div hx-ext="sse" sse-connect="/events" hx-disinherit="hx-target hx-swap"></div>'
            ),
        }

        issues = check_view_transition_safety(template_sources)

        assert len(issues) == 1
        assert issues[0].severity == Severity.WARNING
        assert issues[0].category == "view_transition_scope"
        assert "Remove transition:true from the container" in issues[0].message

    def test_warns_for_view_transition_name_on_broad_live_container(self):
        template_sources = {
            "_layout.html": (
                '<main id="main" hx-boost="true" hx-target="#main">'
                "{% block content %}{% endblock %}"
                "</main>"
                "<style>#main { view-transition-name: page-content; }</style>"
            ),
            "events.html": '<div id="status" hx-swap-oob="outerHTML">ok</div>',
        }

        issues = check_view_transition_safety(template_sources)

        assert len(issues) == 1
        assert issues[0].category == "view_transition_scope"
        assert "#main has view-transition-name" in issues[0].message

    def test_warns_for_inline_view_transition_name_on_broad_live_container(self):
        template_sources = {
            "_layout.html": (
                '<main id="main" style="view-transition-name: page-content" '
                'hx-boost="true" hx-target="#main">'
                "{% block content %}{% endblock %}"
                "</main>"
            ),
            "events.html": '<div id="status" hx-swap-oob="outerHTML">ok</div>',
        }

        issues = check_view_transition_safety(template_sources)

        assert len(issues) == 1
        assert issues[0].category == "view_transition_scope"
        assert "inline view-transition-name" in issues[0].message

    def test_allows_transition_true_without_live_updates(self):
        template_sources = {
            "_layout.html": (
                '<main id="main" hx-boost="true" hx-target="#main" '
                'hx-swap="innerHTML transition:true"></main>'
            ),
        }

        issues = check_view_transition_safety(template_sources)

        assert issues == []

    def test_allows_view_transition_name_on_navigation_only_region(self):
        template_sources = {
            "_layout.html": (
                '<main id="main" hx-boost="true" hx-target="#main">'
                "<style>.story-detail { view-transition-name: page-content; }</style>"
                "</main>"
            ),
            "events.html": '<div id="status" hx-swap-oob="outerHTML">ok</div>',
        }

        issues = check_view_transition_safety(template_sources)

        assert issues == []
