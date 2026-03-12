"""Tests for SSE contract validation — fragments, self-swap, scope, event crossref."""

from chirp import App
from chirp.config import AppConfig
from chirp.contracts import (
    FragmentContract,
    Severity,
    SSEContract,
    check_hypermedia_surface,
    contract,
)
from chirp.contracts.rules_sse import (
    check_sse_connect_scope,
    check_sse_self_swap,
)
from chirp.contracts.rules_swap import collect_broad_targets


class TestSSEFragmentValidation:
    """SSE fragment contract validation in check_hypermedia_surface."""

    def test_valid_sse_fragments(self, tmp_path):
        """SSE route with valid fragment declarations passes."""
        (tmp_path / "chat.html").write_text(
            "{% block message %}<p>msg</p>{% endblock %}{% block status %}<p>ok</p>{% endblock %}"
        )
        app = App(AppConfig(template_dir=str(tmp_path)))

        @app.route("/events")
        @contract(
            returns=SSEContract(
                event_types=frozenset({"message", "status"}),
                fragments=(
                    FragmentContract("chat.html", "message"),
                    FragmentContract("chat.html", "status"),
                ),
            )
        )
        async def events():
            return "ok"

        result = check_hypermedia_surface(app)
        sse_errors = [i for i in result.errors if i.category == "sse"]
        assert len(sse_errors) == 0
        assert result.sse_fragments_validated == 2

    def test_missing_template(self, tmp_path):
        """SSE route referencing a nonexistent template reports ERROR."""
        app = App(AppConfig(template_dir=str(tmp_path)))

        @app.route("/events")
        @contract(
            returns=SSEContract(
                fragments=(FragmentContract("nonexistent.html", "body"),),
            )
        )
        async def events():
            return "ok"

        result = check_hypermedia_surface(app)
        sse_errors = [i for i in result.errors if i.category == "sse"]
        assert len(sse_errors) == 1
        assert "could not be loaded" in sse_errors[0].message

    def test_missing_block(self, tmp_path):
        """SSE route referencing a nonexistent block reports ERROR."""
        (tmp_path / "chat.html").write_text("{% block message %}<p>msg</p>{% endblock %}")
        app = App(AppConfig(template_dir=str(tmp_path)))

        @app.route("/events")
        @contract(
            returns=SSEContract(
                fragments=(FragmentContract("chat.html", "wrong_block"),),
            )
        )
        async def events():
            return "ok"

        result = check_hypermedia_surface(app)
        sse_errors = [i for i in result.errors if i.category == "sse"]
        assert len(sse_errors) == 1
        assert "doesn't exist" in sse_errors[0].message

    def test_empty_fragments_passes(self, tmp_path):
        """SSE route with no fragment declarations passes silently."""
        app = App(AppConfig(template_dir=str(tmp_path)))

        @app.route("/events")
        @contract(returns=SSEContract(event_types=frozenset({"ping"})))
        async def events():
            return "ok"

        result = check_hypermedia_surface(app)
        sse_errors = [i for i in result.errors if i.category == "sse"]
        assert len(sse_errors) == 0
        assert result.sse_fragments_validated == 0


class TestSSESelfSwap:
    """ERROR when sse-swap is on the same element as sse-connect."""

    def test_error_when_sse_swap_on_sse_connect(self):
        template_sources = {
            "chat.html": (
                '<div hx-ext="sse" sse-connect="/chat/stream" '
                'sse-swap="fragment" hx-swap="beforeend">'
                "</div>"
            ),
        }
        issues = check_sse_self_swap(template_sources)
        assert len(issues) == 1
        assert issues[0].severity == Severity.ERROR
        assert issues[0].category == "sse_self_swap"
        assert "querySelectorAll" in issues[0].message
        assert 'sse-swap="fragment"' in issues[0].message

    def test_no_error_when_sse_swap_on_child(self):
        template_sources = {
            "chat.html": (
                '<div hx-ext="sse" sse-connect="/chat/stream">'
                '<span sse-swap="fragment" hx-swap="beforeend"></span>'
                "</div>"
            ),
        }
        issues = check_sse_self_swap(template_sources)
        assert issues == []

    def test_no_error_for_sse_connect_without_swap(self):
        template_sources = {
            "page.html": '<div hx-ext="sse" sse-connect="/events"></div>',
        }
        issues = check_sse_self_swap(template_sources)
        assert issues == []


class TestSSEConnectScope:
    """WARN when sse-connect is inside broad hx-target without hx-disinherit."""

    def test_warns_without_disinherit(self):
        template_sources = {
            "_layout.html": '<body hx-boost="true" hx-target="#app-content"></body>',
            "editor.html": (
                '<div hx-ext="sse" sse-connect="/doc/123/stream">'
                '<span id="status" sse-swap="status">ok</span>'
                "</div>"
            ),
        }
        broad = collect_broad_targets(template_sources)
        issues = check_sse_connect_scope(template_sources, broad)
        assert len(issues) == 1
        assert issues[0].severity == Severity.ERROR
        assert issues[0].category == "sse_scope"
        assert "hx-disinherit" in issues[0].message or "sse_scope" in issues[0].message

    def test_no_warning_with_disinherit(self):
        template_sources = {
            "_layout.html": '<body hx-boost="true" hx-target="#app-content"></body>',
            "editor.html": (
                '<div hx-ext="sse" sse-connect="/doc/123/stream" '
                'hx-disinherit="hx-target hx-swap">'
                '<span id="status" sse-swap="status">ok</span>'
                "</div>"
            ),
        }
        broad = collect_broad_targets(template_sources)
        issues = check_sse_connect_scope(template_sources, broad)
        assert issues == []

    def test_no_warning_when_no_broad_targets(self):
        template_sources = {
            "page.html": (
                '<div hx-ext="sse" sse-connect="/events"><span sse-swap="status"></span></div>'
            ),
        }
        broad = collect_broad_targets(template_sources)
        assert broad == set()
        issues = check_sse_connect_scope(template_sources, broad)
        assert issues == []


class TestSSEEventCrossref:
    """Cross-reference sse-swap values against SSEContract.event_types."""

    def test_warns_for_undeclared_sse_swap(self, tmp_path):
        """sse-swap listens for event not in SSEContract.event_types."""
        (tmp_path / "page.html").write_text(
            '<div hx-ext="sse" sse-connect="/stream">'
            '<span sse-swap="status">ok</span>'
            '<span sse-swap="typo_event">x</span>'
            "</div>"
        )
        app = App(AppConfig(template_dir=str(tmp_path)))

        @app.route("/stream")
        @contract(
            returns=SSEContract(
                event_types=frozenset({"status", "presence"}),
            )
        )
        async def stream():
            return "ok"

        result = check_hypermedia_surface(app)
        crossref = [i for i in result.issues if i.category == "sse_crossref"]
        # typo_event is undeclared (WARNING)
        warnings = [i for i in crossref if i.severity == Severity.WARNING]
        assert len(warnings) == 1
        assert "typo_event" in warnings[0].message

        # presence is declared but has no sse-swap (INFO)
        infos = [i for i in crossref if i.severity == Severity.INFO]
        assert len(infos) == 1
        assert "presence" in infos[0].message

    def test_no_issues_when_events_match(self, tmp_path):
        """All sse-swap values match declared event_types."""
        (tmp_path / "page.html").write_text(
            '<div hx-ext="sse" sse-connect="/stream">'
            '<span sse-swap="status">ok</span>'
            '<span sse-swap="presence">0</span>'
            "</div>"
        )
        app = App(AppConfig(template_dir=str(tmp_path)))

        @app.route("/stream")
        @contract(
            returns=SSEContract(
                event_types=frozenset({"status", "presence"}),
            )
        )
        async def stream():
            return "ok"

        result = check_hypermedia_surface(app)
        crossref = [i for i in result.issues if i.category == "sse_crossref"]
        assert crossref == []

    def test_skipped_when_no_event_types_declared(self, tmp_path):
        """SSEContract without event_types -> no cross-reference."""
        (tmp_path / "page.html").write_text(
            '<div hx-ext="sse" sse-connect="/stream"><span sse-swap="whatever">x</span></div>'
        )
        app = App(AppConfig(template_dir=str(tmp_path)))

        @app.route("/stream")
        @contract(returns=SSEContract())
        async def stream():
            return "ok"

        result = check_hypermedia_surface(app)
        crossref = [i for i in result.issues if i.category == "sse_crossref"]
        assert crossref == []

    def test_handles_kida_urls(self, tmp_path):
        """sse-connect with Kida expressions should match parameterized routes."""
        (tmp_path / "page.html").write_text(
            '<div hx-ext="sse" sse-connect="/doc/{{ doc.id }}/stream">'
            '<span sse-swap="status">ok</span>'
            "</div>"
        )
        app = App(AppConfig(template_dir=str(tmp_path)))

        @app.route("/doc/{doc_id}/stream")
        @contract(
            returns=SSEContract(
                event_types=frozenset({"status", "title"}),
            )
        )
        async def stream(doc_id: str):
            return "ok"

        result = check_hypermedia_surface(app)
        crossref = [i for i in result.issues if i.category == "sse_crossref"]
        # title is declared but has no sse-swap (INFO)
        infos = [i for i in crossref if i.severity == Severity.INFO]
        assert len(infos) == 1
        assert "title" in infos[0].message
