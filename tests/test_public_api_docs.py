"""Tests that public API documentation stays aligned with the code registry."""

import re
import shutil
import subprocess
from collections import defaultdict
from dataclasses import fields
from pathlib import Path

import pytest

import chirp
from chirp import AppConfig

_PUBLIC_API_DOC = Path(__file__).resolve().parents[1] / "docs" / "public-api.md"
_CONFIG_DOC = (
    Path(__file__).resolve().parents[1]
    / "site"
    / "content"
    / "docs"
    / "about"
    / "core-concepts"
    / "configuration.md"
)
_STATUS_SECTIONS = {
    "stable": "Stable Core",
    "provisional": "Provisional Extension Surface",
    "debug": "Debug And Advanced",
}
_BACKTICK_NAME_RE = re.compile(r"`([A-Za-z_][A-Za-z0-9_]*)`")


def _section_body(markdown: str, heading: str) -> str:
    pattern = re.compile(rf"^## {re.escape(heading)}\n(?P<body>.*?)(?=^## |\Z)", re.S | re.M)
    match = pattern.search(markdown)
    assert match is not None, f"docs/public-api.md is missing the '## {heading}' section."
    return match.group("body")


def _documented_api_statuses() -> dict[str, set[str]]:
    markdown = _PUBLIC_API_DOC.read_text()
    return {
        status: set(_BACKTICK_NAME_RE.findall(_section_body(markdown, heading)))
        for status, heading in _STATUS_SECTIONS.items()
    }


def test_public_api_docs_classify_every_export() -> None:
    """The stability tables should match chirp._API_STATUS exactly."""
    documented_by_status = _documented_api_statuses()

    failures: list[str] = []
    for status, heading in _STATUS_SECTIONS.items():
        expected = {name for name, api_status in chirp._API_STATUS.items() if api_status == status}
        documented = documented_by_status[status]
        missing = expected - documented
        extra = documented - expected
        if missing:
            failures.append(f"Add these {status} exports to '## {heading}': {sorted(missing)}")
        if extra:
            failures.append(
                f"Remove or reclassify these names from '## {heading}': {sorted(extra)}"
            )

    assert not failures, "\n".join(failures)


def test_public_api_docs_classify_names_once() -> None:
    """A public name should not appear in multiple stability sections."""
    sections_by_name: dict[str, list[str]] = defaultdict(list)
    for status, names in _documented_api_statuses().items():
        heading = _STATUS_SECTIONS[status]
        for name in names:
            sections_by_name[name].append(heading)

    duplicates = {
        name: headings for name, headings in sections_by_name.items() if len(headings) > 1
    }

    assert not duplicates, (
        f"docs/public-api.md classifies these names in multiple sections: {duplicates}"
    )


@pytest.mark.issue(577)
def test_milo_adapter_is_documented_as_a_provisional_submodule_api() -> None:
    section = _section_body(_PUBLIC_API_DOC.read_text(), "Provisional Submodule APIs")

    for name in (
        "MiloContext",
        "MiloContextProvider",
        "MiloMCPAppAdapter",
        "MiloMCPAppBinding",
        "use_milo",
    ):
        assert section.count(f"`{name}`") == 1
    assert "`chirp.ext.milo`" in section
    assert "not re-exported from `chirp`" in section


def test_configuration_guide_documents_every_app_config_field() -> None:
    """The published config guide should mention every AppConfig field."""
    markdown = _CONFIG_DOC.read_text()
    documented_fields = set(_BACKTICK_NAME_RE.findall(markdown))
    expected_fields = {field.name for field in fields(AppConfig)}

    missing = expected_fields - documented_fields

    assert not missing, (
        "Add these AppConfig fields to "
        "site/content/docs/about/core-concepts/configuration.md: "
        f"{sorted(missing)}"
    )


def _run_git(args: list[str]) -> str:
    git = shutil.which("git")
    if git is None:
        pytest.skip("git is unavailable; branch drift guard needs a checkout")
    result = subprocess.run(
        [git, *args],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        pytest.skip(result.stderr.strip() or "git command failed")
    return result.stdout.strip()


def test_public_api_changes_include_changelog_fragment() -> None:
    """Branch changes to chirp.__init__ should carry release-note context."""
    merge_base = _run_git(["merge-base", "HEAD", "origin/main"])
    changed_files = set(
        filter(
            None,
            _run_git(
                ["diff", "--name-only", "--diff-filter=AM", f"{merge_base}...HEAD"]
            ).splitlines(),
        )
    )
    if "src/chirp/__init__.py" not in changed_files:
        return

    fragments = sorted(
        path
        for path in changed_files
        if path.startswith("changelog.d/")
        and path.endswith(".md")
        and not path.endswith("/README.md")
    )
    assert fragments, (
        "Changing src/chirp/__init__.py changes the top-level public API surface. "
        "Add a changelog fragment under changelog.d/+<slug>.<type>.md."
    )
