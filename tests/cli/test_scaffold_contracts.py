"""Scaffolds must pass ``app.check()`` on a clean freeze.

Invariant 1 from ``.cursor/plans/scaffold-modernization.plan.md`` — every
scaffold mode freezes with zero ERROR-severity contract issues.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.cli.conftest import SCAFFOLD_MODES, run_and_parse, scaffold

_FREEZE_CHECK_CODE = r"""
import json, sys
sys.path.insert(0, ".")
import app as _app
from chirp.contracts import check_hypermedia_surface

_app.app.freeze()
result = check_hypermedia_surface(_app.app)
errors = [
    {
        "category": i.category,
        "message": i.message,
        "template": i.template,
        "route": i.route,
    }
    for i in result.errors
]
print(json.dumps({
    "ok": result.ok,
    "error_count": len(errors),
    "warning_count": len(result.warnings),
    "errors": errors,
}))
"""


@pytest.mark.parametrize("mode", SCAFFOLD_MODES)
def test_scaffold_freezes_with_no_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    project = scaffold(tmp_path, monkeypatch, mode=mode)
    result = run_and_parse(project, _FREEZE_CHECK_CODE)
    assert result.returncode == 0, (
        f"Scaffold '{mode}' subprocess failed:\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )
    assert result.payload.get("ok") is True, (
        f"Scaffold '{mode}' freeze produced ERROR issues: "
        f"{result.payload.get('errors')}"
    )
    assert result.payload["error_count"] == 0
