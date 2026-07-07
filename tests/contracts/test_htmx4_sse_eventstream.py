"""End-to-end htmx 4 SSE markup and EventStream agreement (#553)."""

from pathlib import Path

import pytest

from chirp import App, AppConfig, EventStream, Fragment, Template
from chirp.app.htmx_manifest import HTMX4_PREVIEW_VERSION
from chirp.contracts import check_hypermedia_surface
from chirp.testing import TestClient, assert_sse_wired

pytestmark = pytest.mark.issue(553)


def _app(template_dir: Path) -> App:
    (template_dir / "page.html").write_text(
        """{% from "chirp/sse.html" import sse_scope %}
<!doctype html>
<html lang="en">
<head><title>SSE preview</title></head>
<body>
  {{ sse_scope("/events", swap="feed") }}
  {% block item %}<span>{{ message ?? "seed" }}</span>{% endblock %}
</body>
</html>
""",
        encoding="utf-8",
    )
    app = App(
        AppConfig(
            debug=True,
            htmx=True,
            htmx_version=HTMX4_PREVIEW_VERSION,
            template_dir=template_dir,
        )
    )

    @app.route("/")
    def index():
        return Template("page.html")

    @app.route("/events", referenced=True)
    def events():
        async def gen():
            yield Fragment("page.html", "item", target="feed", message="updated")

        return EventStream(gen())

    return app


async def test_preview_macro_and_eventstream_share_native_dialect(tmp_path: Path) -> None:
    app = _app(tmp_path)

    async with TestClient(app) as client:
        page = await client.get("/")
        stream = await client.sse("/events", request_type="partial", max_events=1)
        await assert_sse_wired(client, "/", "/events", max_events=1)

    assert 'hx-sse:connect="/events"' in page.text
    assert 'hx-target="#feed"' in page.text
    assert 'id="feed"' in page.text
    assert "sse-connect=" not in page.text
    assert "sse-swap=" not in page.text
    assert stream.events[0].event is None
    assert stream.events[0].data == (
        '<hx-partial hx-target="#feed"><span>updated</span></hx-partial>'
    )


def test_preview_macro_does_not_trigger_legacy_drift_diagnostic(tmp_path: Path) -> None:
    app = _app(tmp_path)
    app._ensure_frozen()
    result = check_hypermedia_surface(app)

    drift = [
        issue
        for issue in result.issues
        if issue.category == "htmx_compatibility"
        and ("sse-connect" in issue.message or "sse-swap" in issue.message)
    ]
    assert drift == []
