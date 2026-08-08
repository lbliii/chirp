"""``chirp skill publish`` — run the Orrery check + freeze + smoke gate."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from chirp.cli._inspection import (
    InspectionResult,
    emit_terminal_result,
    inspection_error,
    resolution_error,
)
from chirp.cli._resolve import resolve_app
from chirp.skill.publish import format_publish_receipt, run_publish_gate
from chirp.skill.smoke import FIXTURE_CORPUS, CorpusPrompt


def _load_corpus(
    path: str | None, *, use_fixture: bool
) -> tuple[CorpusPrompt, ...] | InspectionResult:
    if use_fixture:
        return FIXTURE_CORPUS
    if not path:
        return inspection_error(
            code="CHIRP_SKILL_PUBLISH_CORPUS",
            message="Smoke corpus required: pass --corpus PATH or --fixture",
            suggestion=(
                "Provide a JSON corpus file, or use --fixture with the "
                "canonical fixture-echo skill from chirp.skill.smoke."
            ),
        )
    corpus_path = Path(path)
    try:
        raw = json.loads(corpus_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return inspection_error(
            code="CHIRP_SKILL_PUBLISH_CORPUS",
            message=f"Could not read smoke corpus {path!r}: {exc}",
            suggestion="Pass a JSON array of CorpusPrompt objects (id, prompt, tool, ...).",
            context={"corpus": path},
        )
    if not isinstance(raw, list) or not raw:
        return inspection_error(
            code="CHIRP_SKILL_PUBLISH_CORPUS",
            message=f"Smoke corpus {path!r} must be a non-empty JSON array",
            suggestion="Each entry needs id, prompt, tool; optional arguments and required_facts.",
            context={"corpus": path},
        )
    try:
        return tuple(
            CorpusPrompt(
                id=str(entry["id"]),
                prompt=str(entry["prompt"]),
                tool=str(entry["tool"]),
                arguments=dict(entry.get("arguments") or {}),
                required_facts=tuple(entry.get("required_facts") or ()),
            )
            for entry in raw
        )
    except (KeyError, TypeError, ValueError) as exc:
        return inspection_error(
            code="CHIRP_SKILL_PUBLISH_CORPUS",
            message=f"Invalid smoke corpus entry in {path!r}: {exc}",
            suggestion="Each entry needs id, prompt, tool; optional arguments and required_facts.",
            context={"corpus": path},
        )


def collect_skill_publish_result(
    app_import: str,
    *,
    corpus: str | None = None,
    fixture: bool = False,
    warnings_as_errors: bool = False,
    json_output: bool = False,
) -> InspectionResult:
    """Resolve *app_import*, run the publish gate, and return a structured result."""
    loaded = _load_corpus(corpus, use_fixture=fixture)
    if isinstance(loaded, InspectionResult):
        return loaded

    try:
        app = resolve_app(app_import)
    except (ModuleNotFoundError, AttributeError, TypeError) as exc:
        return resolution_error(app_import, exc)

    receipt = run_publish_gate(
        app,
        loaded,
        warnings_as_errors=warnings_as_errors,
    )
    payload: dict[str, Any] = receipt.to_dict()
    terminal_text = (
        json.dumps(payload, indent=2) if json_output else format_publish_receipt(receipt)
    )
    return InspectionResult(
        payload,
        terminal_text=terminal_text,
        exit_code=0 if receipt.passed else 1,
    )


def run_skill_publish(args: Any) -> None:
    """CLI entry for ``chirp skill publish``."""
    emit_terminal_result(
        collect_skill_publish_result(
            args.app,
            corpus=getattr(args, "corpus", None),
            fixture=bool(getattr(args, "fixture", False)),
            warnings_as_errors=bool(getattr(args, "warnings_as_errors", False)),
            json_output=bool(getattr(args, "json", False)),
        )
    )
