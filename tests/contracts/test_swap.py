"""Tests for swap safety — broad hx-target + mutating requests."""

from chirp.contracts import Severity
from chirp.contracts.rules_swap import check_swap_safety


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
