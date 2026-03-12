"""Tests for island mount extraction and validation."""

from chirp.contracts import Severity
from chirp.contracts.rules_islands import check_island_mounts, extract_island_mounts


class TestIslandMountExtraction:
    def test_extract_mount_with_props_and_src(self):
        html = (
            '<div data-island="chart" id="sales-chart" '
            'data-island-version="1" '
            'data-island-src="/static/chart.js" data-island-props="{&quot;series&quot;:[1,2]}"></div>'
        )
        mounts = extract_island_mounts(html)
        assert len(mounts) == 1
        assert mounts[0]["name"] == "chart"
        assert mounts[0]["mount_id"] == "sales-chart"
        assert mounts[0]["version"] == "1"
        assert mounts[0]["src"] == "/static/chart.js"
        assert mounts[0]["primitive"] is None

    def test_extract_mount_with_primitive(self):
        html = '<div data-island="grid_state" data-island-primitive="grid_state"></div>'
        mounts = extract_island_mounts(html)
        assert len(mounts) == 1
        assert mounts[0]["primitive"] == "grid_state"

    def test_empty_when_no_mounts(self):
        assert extract_island_mounts("<div>No island</div>") == []


class TestIslandMountValidation:
    def test_malformed_props_json_errors(self):
        sources = {"index.html": '<div data-island="chart" data-island-props="{oops"></div>'}
        issues = check_island_mounts(sources, strict=False)
        assert len(issues) == 1
        assert issues[0].severity == Severity.ERROR
        assert issues[0].category == "islands"

    def test_missing_id_warns_in_strict_mode(self):
        sources = {
            "index.html": (
                '<div data-island="editor" data-island-version="1" '
                'data-island-props="{&quot;a&quot;:1}"></div>'
            )
        }
        issues = check_island_mounts(sources, strict=True)
        assert len(issues) == 1
        assert issues[0].severity == Severity.WARNING
        assert issues[0].category == "islands"

    def test_valid_mount_has_no_issues(self):
        sources = {
            "index.html": (
                '<div data-island="editor" id="editor-root" '
                'data-island-version="1" '
                'data-island-props="{&quot;a&quot;:1}"></div>'
            )
        }
        issues = check_island_mounts(sources, strict=True)
        assert issues == []

    def test_missing_version_warns_in_strict_mode(self):
        sources = {
            "index.html": (
                '<div data-island="editor" id="editor-root" '
                'data-island-props="{&quot;a&quot;:1}"></div>'
            )
        }
        issues = check_island_mounts(sources, strict=True)
        assert len(issues) == 1
        assert issues[0].severity == Severity.WARNING
        assert "data-island-version" in issues[0].message

    def test_invalid_version_errors(self):
        sources = {"index.html": '<div data-island="editor" data-island-version="1 beta"></div>'}
        issues = check_island_mounts(sources, strict=False)
        assert len(issues) == 1
        assert issues[0].severity == Severity.ERROR
        assert "invalid data-island-version" in issues[0].message

    def test_unsafe_src_errors(self):
        sources = {
            "index.html": '<div data-island="editor" data-island-src="javascript:alert(1)"></div>'
        }
        issues = check_island_mounts(sources, strict=False)
        assert len(issues) == 1
        assert issues[0].severity == Severity.ERROR
        assert "unsafe data-island-src" in issues[0].message

    def test_primitive_required_props_error(self):
        sources = {
            "index.html": (
                '<div data-island="grid_state" data-island-primitive="grid_state" '
                'data-island-props="{&quot;stateKey&quot;:&quot;grid&quot;}"></div>'
            )
        }
        issues = check_island_mounts(sources, strict=False)
        assert len(issues) == 1
        assert issues[0].severity == Severity.ERROR
        assert "required props: columns" in issues[0].message

    def test_primitive_object_props_required(self):
        sources = {
            "index.html": (
                '<div data-island="wizard_state" data-island-primitive="wizard_state" '
                'data-island-props="[1,2,3]"></div>'
            )
        }
        issues = check_island_mounts(sources, strict=False)
        assert len(issues) == 1
        assert issues[0].severity == Severity.ERROR
        assert "expects object-like props" in issues[0].message

    def test_primitive_missing_props_errors(self):
        sources = {
            "index.html": '<div data-island="upload_state" data-island-primitive="upload_state"></div>'
        }
        issues = check_island_mounts(sources, strict=False)
        assert len(issues) == 1
        assert issues[0].severity == Severity.ERROR
        assert "must define data-island-props" in issues[0].message
