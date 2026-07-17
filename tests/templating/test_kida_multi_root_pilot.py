"""Consumer-owned proof for Kida's explicit multi-root inspection contract."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from kida import Environment, FileSystemLoader, PrefixLoader, TemplateMetadata

from chirp.templating.kida_adapter import KidaAdapter
from chirp.templating.oob_registry import OOBRegionConfig, OOBRegistry

_PILOT_ENV = "CHIRP_KIDA_MULTI_ROOT_PILOT"

try:
    from kida.analysis import AdviceContext, profile_source
    from kida.inspection import (
        TemplateRoot,
        advise_encapsulation_roots,
        diagnose_roots,
        inspect_components,
    )
except ImportError as exc:
    if exc.name not in {"kida.analysis", "kida.inspection"} or os.environ.get(_PILOT_ENV) == "1":
        raise
    pytest.skip(
        "Kida's multi-root adapter-advice API is not released yet",
        allow_module_level=True,
    )

_FIXTURE = Path(__file__).parent / "fixtures" / "kida_multi_root"
_CHIRP_ROOT = _FIXTURE / "chirp"
_APP_ROOT = _FIXTURE / "app"


def _roots() -> tuple[TemplateRoot, TemplateRoot]:
    return (
        TemplateRoot("chirp", _CHIRP_ROOT),
        TemplateRoot("app", _APP_ROOT),
    )


def _environment() -> Environment:
    return Environment(
        loader=PrefixLoader(
            {
                "chirp": FileSystemLoader(_CHIRP_ROOT),
                "app": FileSystemLoader(_APP_ROOT),
            }
        ),
        bytecode_cache=False,
    )


def _chirp_oob_advice_context(
    adapter: KidaAdapter,
    source: str,
    *,
    name: str,
    oob_registry: OOBRegistry,
    repeated_consumers: frozenset[str],
) -> tuple[AdviceContext, ...]:
    """Translate Chirp-owned OOB facts without adding Chirp semantics to Kida."""
    metadata = adapter.template_metadata(name)
    if not isinstance(metadata, TemplateMetadata):
        return ()

    contexts: list[AdviceContext] = []
    profiles = profile_source(source, name=name)
    for profile in profiles.profiles:
        if profile.kind != "block" or profile.name is None:
            continue
        block = metadata.blocks.get(profile.name)
        config = oob_registry.get(profile.name)
        transport = block.get_modifier("transport") if block is not None else None
        if config is None or transport is None or transport.value != "oob":
            continue
        facts: list[tuple[str, str | bool]] = [
            ("chirp.swap", config.swap),
            ("preserve_boundary", True),
            ("response_boundary", True),
            ("role", "oob-response"),
        ]
        if profile.name in repeated_consumers:
            facts.append(("consumer_context", "repeated"))
        contexts.append(AdviceContext(profile.span, tuple(facts)))
    return tuple(contexts)


@pytest.mark.issue(860)
def test_explicit_roots_work_through_chirp_without_chirp_ui() -> None:
    if os.environ.get(_PILOT_ENV) == "1":
        assert importlib.util.find_spec("chirp_ui") is None

    command = [
        sys.executable,
        "-m",
        "kida",
        "check",
        "--root",
        f"chirp={_CHIRP_ROOT}",
        "--root",
        f"app={_APP_ROOT}",
        "--validate-calls",
        "--format",
        "json",
    ]
    completed = subprocess.run(command, check=False, capture_output=True, text=True)

    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout)["diagnostics"] == []

    environment = _environment()
    adapter = KidaAdapter(environment)
    rendered = adapter.render_template("app/page.html", {})
    assert '<article class="card">Inbox</article>' in rendered

    forward = inspect_components(_roots(), environment=environment)
    reverse = inspect_components(tuple(reversed(_roots())), environment=environment)

    assert forward == reverse
    assert forward.partial is False
    assert forward.diagnostics == ()
    assert [
        (record.owner, record.template, record.metadata.name) for record in forward.components
    ] == [
        ("app", "app/components.html", "notice"),
        ("chirp", "chirp/card.html", "card"),
    ]
    assert [record.source_path for record in forward.components] == [
        str((_APP_ROOT / "components.html").resolve()),
        str((_CHIRP_ROOT / "card.html").resolve()),
    ]
    assert (_CHIRP_ROOT / "card.css").is_file()


@pytest.mark.issue(860)
def test_explicit_root_failures_keep_actionable_ownership(tmp_path: Path) -> None:
    duplicate = diagnose_roots(
        (
            TemplateRoot("app", _APP_ROOT),
            TemplateRoot("app", _CHIRP_ROOT),
        )
    )
    missing_path = tmp_path / "missing"
    missing = diagnose_roots((TemplateRoot("missing", missing_path),))

    malformed_root = tmp_path / "malformed"
    malformed_root.mkdir()
    malformed_path = malformed_root / "broken.html"
    malformed_path.write_text("{% def broken( %}", encoding="utf-8")
    malformed = diagnose_roots((TemplateRoot("broken", malformed_root),))

    assert duplicate.partial is True
    assert [diagnostic.code for diagnostic in duplicate.diagnostics] == ["K-TPL-005"]
    assert "duplicate template root namespace 'app'" in duplicate.diagnostics[0].message

    assert missing.partial is True
    assert [diagnostic.code for diagnostic in missing.diagnostics] == ["K-TPL-005"]
    assert dict(missing.diagnostics[0].metadata) == {
        "owner": "missing",
        "source_path": str(missing_path.resolve()),
    }

    assert malformed.partial is True
    assert len(malformed.diagnostics) == 1
    assert malformed.diagnostics[0].span.path == "broken/broken.html"
    assert dict(malformed.diagnostics[0].metadata) == {
        "owner": "broken",
        "source_path": str(malformed_path),
    }


def test_chirp_oob_context_preserves_route_response_and_exposes_nested_candidate() -> None:
    name = "app/messages.html"
    source = (_APP_ROOT / "messages.html").read_text(encoding="utf-8")
    environment = _environment()
    adapter = KidaAdapter(environment)
    registry = OOBRegistry()
    registry.register(
        "messages_oob",
        OOBRegionConfig(target_id="messages", swap="innerHTML"),
    )
    registry.freeze()
    contexts = _chirp_oob_advice_context(
        adapter,
        source,
        name=name,
        oob_registry=registry,
        repeated_consumers=frozenset({"messages_oob"}),
    )

    without_chirp_context = advise_encapsulation_roots(_roots(), environment=environment)
    with_chirp_context = advise_encapsulation_roots(
        _roots(),
        environment=environment,
        context=contexts,
    )

    assert without_chirp_context.diagnostics == ()
    assert len(contexts) == 1
    assert [item.code for item in with_chirp_context.diagnostics] == ["K-MOD-102"]
    diagnostic = with_chirp_context.diagnostics[0]
    block_span = contexts[0].span
    assert diagnostic.span.path == name
    assert diagnostic.span != block_span
    assert diagnostic.span.start is not None
    assert diagnostic.span.end is not None
    assert block_span.start is not None
    assert block_span.end is not None
    assert block_span.start.line <= diagnostic.span.start.line
    assert diagnostic.span.end.line <= block_span.end.line
    assert "preserves the outer boundary" in diagnostic.notes[-1]
    advice_facts = json.loads(dict(diagnostic.metadata)["advice_context"])[0]["facts"]
    assert advice_facts == {
        "consumer_context": "repeated",
        "preserve_boundary": True,
        "response_boundary": True,
        "role": "oob-response",
    }

    metadata = adapter.template_metadata(name)
    assert isinstance(metadata, TemplateMetadata)
    response_block = metadata.blocks["messages_oob"]
    assert response_block.get_modifier("transport").value == "oob"
    assert registry.registered_blocks == frozenset({"messages_oob"})
    assert registry.resolve_serialization("messages") == ("innerHTML", True)
    render_context = {
        "current_user": {"id": "u1"},
        "messages": [
            {
                "author": {"avatar": "/ada.png", "id": "u1", "name": "Ada"},
                "body": "Adapter context stays downstream.",
                "created_at": "2026-07-17T19:00:00Z",
                "id": "m1",
                "permalink": "/messages/m1",
                "relative_time": "now",
            }
        ],
    }
    route_html = adapter.render_template(name, render_context)
    response_html = adapter.render_block(name, "messages_oob", render_context)
    assert 'class="message-row"' in route_html
    assert response_html.strip() in route_html
    assert ">Edit</button>" in response_html
