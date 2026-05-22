"""Tests for typed return traces."""

import base64
import json
from pathlib import Path

from chirp import (
    OOB,
    Action,
    App,
    AppConfig,
    EventStream,
    Fragment,
    Page,
    Stream,
    Suspense,
    Template,
    ValidationError,
)
from chirp.testing import TestClient


def _write_templates(path: Path) -> None:
    (path / "page.html").write_text(
        "{% block page_root %}<html><body>{% block content %}{{ message }}{% end %}</body></html>{% end %}"
    )
    (path / "fragment.html").write_text(
        "{% block item %}<div id='item'>{{ message }}</div>{% end %}"
        "{% block extra %}<div id='extra'>{{ count }}</div>{% end %}"
    )


def _decode_trace(value: str | None) -> dict:
    assert value is not None
    raw = base64.b64decode(value).decode("utf-8")
    return json.loads(raw)


def _debug_app(tmp_path: Path) -> App:
    _write_templates(tmp_path)
    return App(AppConfig(debug=True, skip_contract_checks=True, template_dir=tmp_path))


async def test_template_return_trace_header(tmp_path: Path) -> None:
    app = _debug_app(tmp_path)

    @app.route("/")
    def index():
        return Template("page.html", message="hello")

    async with TestClient(app) as client:
        response = await client.get("/")

    trace = _decode_trace(response.header("X-Chirp-Return-Trace"))
    assert trace["return_type"] == "Template"
    assert trace["category"] == "template"
    assert trace["template"] == "page.html"
    assert trace["render_intent"] == "full_page"


async def test_fragment_return_trace_header(tmp_path: Path) -> None:
    app = _debug_app(tmp_path)

    @app.route("/fragment")
    def fragment():
        return Fragment("fragment.html", "item", target="item", message="hello")

    async with TestClient(app) as client:
        response = await client.fragment("/fragment", target="item")

    trace = _decode_trace(response.header("X-Chirp-Return-Trace"))
    assert trace["return_type"] == "Fragment"
    assert trace["category"] == "fragment"
    assert trace["block"] == "item"
    assert trace["target"] == "item"
    assert trace["is_htmx"] is True


async def test_page_return_trace_uses_render_plan_decision(tmp_path: Path) -> None:
    app = _debug_app(tmp_path)

    @app.route("/page")
    def page():
        return Page("page.html", "content", page_block_name="page_root", message="hello")

    async with TestClient(app) as client:
        response = await client.fragment("/page", target="content")

    trace = _decode_trace(response.header("X-Chirp-Return-Trace"))
    assert trace["return_type"] == "PageComposition"
    assert trace["category"] == "page"
    assert trace["template"] == "page.html"
    assert trace["block"] == "content"
    assert trace["render_intent"] == "fragment"


async def test_oob_return_trace_is_final_return_type(tmp_path: Path) -> None:
    app = _debug_app(tmp_path)

    @app.route("/oob")
    def oob():
        return OOB(
            Fragment("fragment.html", "item", message="hello"),
            Fragment("fragment.html", "extra", count=1),
        )

    async with TestClient(app) as client:
        response = await client.fragment("/oob", target="item")

    trace = _decode_trace(response.header("X-Chirp-Return-Trace"))
    assert trace["return_type"] == "OOB"
    assert trace["category"] == "oob"
    assert "oob_fragments=1" in trace["notes"]


async def test_action_and_validation_return_traces(tmp_path: Path) -> None:
    app = _debug_app(tmp_path)

    @app.route("/action")
    def action():
        return Action(trigger="saved")

    @app.route("/invalid")
    def invalid():
        return ValidationError("fragment.html", "item", retarget="#item", message="bad")

    async with TestClient(app) as client:
        action_response = await client.fragment("/action")
        invalid_response = await client.fragment("/invalid", target="item")

    action_trace = _decode_trace(action_response.header("X-Chirp-Return-Trace"))
    invalid_trace = _decode_trace(invalid_response.header("X-Chirp-Return-Trace"))
    assert action_trace["return_type"] == "Action"
    assert action_trace["status"] == 204
    assert invalid_trace["return_type"] == "ValidationError"
    assert invalid_trace["status"] == 422
    assert invalid_trace["target"] == "#item"


async def test_stream_and_suspense_return_traces(tmp_path: Path) -> None:
    app = _debug_app(tmp_path)

    @app.route("/stream")
    def stream():
        return Stream("page.html", message="hello")

    @app.route("/suspense")
    def suspense():
        return Suspense("page.html", message="hello")

    async with TestClient(app) as client:
        stream_response = await client.get("/stream")
        suspense_response = await client.get("/suspense")

    stream_trace = _decode_trace(stream_response.header("X-Chirp-Return-Trace"))
    suspense_trace = _decode_trace(suspense_response.header("X-Chirp-Return-Trace"))
    assert stream_trace["return_type"] == "Stream"
    assert stream_trace["streaming"] is True
    assert suspense_trace["return_type"] == "Suspense"
    assert suspense_trace["category"] == "suspense"
    assert suspense_trace["streaming"] is True


async def test_eventstream_return_trace_header(tmp_path: Path) -> None:
    app = _debug_app(tmp_path)

    @app.route("/events")
    def events():
        async def gen():
            yield "hello"

        return EventStream(gen())

    async with TestClient(app) as client:
        response = await client.sse("/events", max_events=1)

    trace = _decode_trace(response.headers.get("x-chirp-return-trace"))
    assert trace["return_type"] == "EventStream"
    assert trace["category"] == "eventstream"
    assert trace["streaming"] is True
    assert trace["sse"] is True
