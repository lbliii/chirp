"""Examples with in-place htmx forms must exercise the htmx client in tests.

Plain POST tests can pass while hx-target swaps are broken — the llm_minimal
research showed CI green + browser broken. This gate applies to examples with
``hx-post``/``hx-*`` mutation + explicit ``hx-target`` unless exempted.
"""

import re
from pathlib import Path

import pytest

_EXAMPLES_ROOT = Path(__file__).resolve().parent.parent / "examples"
_APP_FILES = sorted(_EXAMPLES_ROOT.rglob("app.py"))
_IDS = [str(p.parent.relative_to(_EXAMPLES_ROOT)) for p in _APP_FILES]

_HTMX_INPLACE = re.compile(
    r"<(?:form|button|a|div|span|input)\b[^>]*\bhx-(?:post|put|patch|delete)\s*=[^>]*"
    r"\bhx-target\s*=\s*[\"']#[^\"']+[\"']",
    re.IGNORECASE | re.DOTALL,
)
_HTMX_INPLACE_REV = re.compile(
    r"<(?:form|button|a|div|span|input)\b[^>]*\bhx-target\s*=\s*[\"']#[^\"']+[\"'][^>]*"
    r"\bhx-(?:post|put|patch|delete)\s*=",
    re.IGNORECASE | re.DOTALL,
)

# Legacy examples — track debt in issues; new examples must not be added here.
_HTMX_TEST_EXEMPT = frozenset(
    {
        "chirpui/contacts_shell",
        "chirpui/llm_playground",
        "chirpui/rag_demo",
        "chirpui/sortable_reorder",
        "standalone/contacts",
        "standalone/htmx_managed",
        "standalone/mutation_result",
        "standalone/ollama",
        "standalone/optimistic_apply",
        "standalone/reactive_tasks",
        "standalone/tools",
        "standalone/tools_hitl",
    }
)


def _example_html(example_dir: Path) -> str:
    return "".join(p.read_text() for p in example_dir.rglob("*.html"))


def _has_inplace_htmx(html: str) -> bool:
    return bool(_HTMX_INPLACE.search(html) or _HTMX_INPLACE_REV.search(html))


def _tests_cover_htmx(example_dir: Path) -> bool:
    parts: list[str] = []
    test_app = example_dir / "test_app.py"
    if test_app.is_file():
        parts.append(test_app.read_text())
    tests_dir = example_dir / "tests"
    if tests_dir.is_dir():
        parts.extend(path.read_text() for path in tests_dir.glob("*.py"))
    combined = "\n".join(parts)
    return "HX-Request" in combined or "hx-request" in combined.lower()


@pytest.mark.parametrize("app_path", _APP_FILES, ids=_IDS)
def test_inplace_htmx_examples_cover_htmx_client(app_path: Path) -> None:
    example_dir = app_path.parent
    rel = str(example_dir.relative_to(_EXAMPLES_ROOT))
    if rel in _HTMX_TEST_EXEMPT:
        pytest.skip("legacy example exempt from htmx client test gate")
    if not _has_inplace_htmx(_example_html(example_dir)):
        pytest.skip("no in-place htmx mutation forms")
    assert _tests_cover_htmx(example_dir), (
        f"{rel} uses hx-* mutation with hx-target but test_app.py (or tests/) "
        "never sends HX-Request. Add a TestClient POST with HX-Request headers."
    )
