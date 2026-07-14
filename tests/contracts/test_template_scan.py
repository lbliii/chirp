"""Tests for template scan — extraction, references, and physical identity."""

from pathlib import Path

import pytest
from kida import (
    ChoiceLoader,
    DictLoader,
    Environment,
    FileSystemLoader,
    FunctionLoader,
    PackageLoader,
)

from chirp.contracts.template_scan import (
    extract_legacy_action_contracts,
    extract_targets_from_source,
    extract_template_references,
    load_template_inventory,
    resolve_template_reference,
)


@pytest.mark.issue(707)
def test_nested_choice_loader_canonicalizes_one_physical_file_by_reference(
    tmp_path: Path,
) -> None:
    nested = tmp_path / "templates" / "partials"
    nested.mkdir(parents=True)
    (nested / "x.html").write_text("<div>x</div>", encoding="utf-8")
    env = Environment(
        loader=ChoiceLoader([FileSystemLoader(tmp_path), FileSystemLoader(tmp_path / "templates")])
    )

    inventory = load_template_inventory(env)

    assert set(inventory.sources) == {
        "partials/x.html",
        "templates/partials/x.html",
    }
    for referenced in ("partials/x.html", "templates/partials/x.html"):
        scan = inventory.canonicalize({referenced})
        assert list(scan.sources) == [referenced]
        assert scan.alias_to_canonical == {
            "partials/x.html": referenced,
            "templates/partials/x.html": referenced,
        }
        assert scan.aliases_by_canonical[referenced] == (
            "partials/x.html",
            "templates/partials/x.html",
        )
        assert scan.sources["partials/x.html"] == "<div>x</div>"
        assert scan.sources["templates/partials/x.html"] == "<div>x</div>"


@pytest.mark.issue(707)
def test_identical_content_at_distinct_paths_keeps_distinct_identity(tmp_path: Path) -> None:
    (tmp_path / "a.html").write_text("same", encoding="utf-8")
    (tmp_path / "b.html").write_text("same", encoding="utf-8")
    inventory = load_template_inventory(Environment(loader=FileSystemLoader(tmp_path)))

    scan = inventory.canonicalize({"a.html"})

    assert set(scan.sources) == {"a.html", "b.html"}
    assert scan.alias_to_canonical == {"a.html": "a.html", "b.html": "b.html"}


@pytest.mark.issue(707)
def test_nonfilesystem_loaders_fall_back_to_logical_identity() -> None:
    dict_inventory = load_template_inventory(
        Environment(loader=DictLoader({"a.html": "same", "b.html": "same"}))
    )
    package_inventory = load_template_inventory(
        Environment(loader=PackageLoader("chirp.templating", "macros"))
    )
    function_inventory = load_template_inventory(
        Environment(loader=FunctionLoader(lambda name: f"source:{name}"))
    )

    dict_scan = dict_inventory.canonicalize(set())
    package_scan = package_inventory.canonicalize(set())

    assert set(dict_scan.sources) == {"a.html", "b.html"}
    assert all(len(aliases) == 1 for aliases in dict_scan.aliases_by_canonical.values())
    assert package_scan.sources
    assert len(package_scan.sources) == len(package_inventory.sources)
    assert all(len(aliases) == 1 for aliases in package_scan.aliases_by_canonical.values())
    assert function_inventory.sources == {}


class TestExtractTargets:
    """Extract htmx targets from template HTML source."""

    def test_hx_get(self):
        html = '<div hx-get="/api/search"></div>'
        targets = extract_targets_from_source(html)
        assert len(targets) == 1
        assert targets[0] == ("hx-get", "/api/search", None)

    def test_hx_post(self):
        html = '<button hx-post="/submit"></button>'
        targets = extract_targets_from_source(html)
        assert targets[0] == ("hx-post", "/submit", None)

    def test_sse_connect_dialects(self):
        html = '<div sse-connect="/legacy"></div><div hx-sse:connect="/native"></div>'
        targets = extract_targets_from_source(html)
        assert ("sse-connect", "/legacy", None) in targets
        assert ("hx-sse:connect", "/native", None) in targets

    def test_form_action_post(self):
        html = '<form action="/login" method="post"></form>'
        targets = extract_targets_from_source(html)
        assert targets[0] == ("action", "/login", "POST")

    def test_form_action_get(self):
        html = '<form action="/skills" method="get" class="chirpui-form"></form>'
        targets = extract_targets_from_source(html)
        assert targets[0] == ("action", "/skills", "GET")

    def test_multiple_targets(self):
        html = """
        <div hx-get="/api/items"></div>
        <button hx-post="/api/items" hx-target="#list"></button>
        <form action="/search"></form>
        """
        targets = extract_targets_from_source(html)
        assert len(targets) == 3
        assert targets[2] == ("action", "/search", "GET")

    def test_form_action_omitted(self):
        html = '<form action="/search"></form>'
        targets = extract_targets_from_source(html)
        assert targets[0] == ("action", "/search", "GET")

    def test_form_action_dialog(self):
        html = '<form action="/x" method="dialog"></form>'
        targets = extract_targets_from_source(html)
        assert targets[0] == ("action", "/x", "GET")

    def test_ignores_template_expressions(self):
        html = "<div hx-get=\"{{ url_for('search') }}\"></div>"
        targets = extract_targets_from_source(html)
        assert len(targets) == 0

    def test_ignores_anchors(self):
        html = '<div hx-get="#section"></div>'
        targets = extract_targets_from_source(html)
        assert len(targets) == 0

    def test_single_quotes(self):
        html = "<div hx-get='/api/data'></div>"
        targets = extract_targets_from_source(html)
        assert targets[0] == ("hx-get", "/api/data", None)

    def test_ignores_kida_tilde_concatenation_in_attrs(self):
        """Kida attrs='hx-post="/chains/' ~ id ~ '/add-step"' must not truncate to /chains/."""
        html = "attrs='hx-post=\"/chains/' ~ chain_id ~ '/add-step\" hx-target=\"#step-list\"'"
        targets = extract_targets_from_source(html)
        assert len(targets) == 0

    def test_ignores_kida_variable_in_url(self):
        html = '<div hx-post="/chains/{{ id }}/add"></div>'
        targets = extract_targets_from_source(html)
        assert len(targets) == 0

    def test_extracts_attrs_map_hx_post_literal(self):
        html = '{{ form("/x", attrs_map={"hx-post": "/config/set", "hx-target": "#result"}) }}'
        targets = extract_targets_from_source(html)
        assert ("hx-post", "/config/set", None) in targets

    def test_extracts_attrs_map_action_literal(self):
        html = '{{ form("/x", attrs_map={"action": "/skills"}) }}'
        targets = extract_targets_from_source(html)
        assert ("action", "/skills", None) in targets

    def test_extracts_confirm_dialog_target(self):
        html = '{{ confirm_dialog("del", confirm_url="/items/1", confirm_method="DELETE") }}'
        targets = extract_targets_from_source(html)
        assert ("confirm_url", "/items/1", "DELETE") in targets

    def test_ignores_confirm_dialog_target_with_kida_concat(self):
        html = (
            '{{ confirm_dialog("del", confirm_url="/contacts/" ~ contact.id ~ "/delete", '
            'confirm_method="DELETE") }}'
        )
        targets = extract_targets_from_source(html)
        assert targets == []

    def test_ignores_attrs_map_hx_post_with_kida_concat(self):
        html = '{{ form("/x", attrs_map={"hx-post": "/chains/" ~ chain_id ~ "/add-step"}) }}'
        targets = extract_targets_from_source(html)
        assert len(targets) == 0

    def test_ignores_attrs_map_unsafe_or_anchor_urls(self):
        html = '{{ btn("X", attrs_map={"hx-get": "#tab-1", "hx-post": "javascript:alert(1)"}) }}'
        targets = extract_targets_from_source(html)
        assert len(targets) == 0

    def test_empty_source(self):
        assert extract_targets_from_source("") == []

    def test_extracts_legacy_action_contract_name(self):
        html = '{{ btn("Update", action="update-collection") }}'
        assert extract_legacy_action_contracts(html) == {"update-collection"}

    def test_ignores_action_paths_for_legacy_contract_scan(self):
        html = '<form action="/login" method="post"></form>'
        assert extract_legacy_action_contracts(html) == set()


class TestExtractTemplateReferences:
    """Extract template references from Kida template source."""

    def test_extends(self):
        source = '{% extends "base.html" %}'
        assert extract_template_references(source) == {"base.html"}

    def test_include(self):
        source = '{% include "partials/header.html" %}'
        assert extract_template_references(source) == {"partials/header.html"}

    def test_from_import(self):
        source = '{% from "macros/forms.html" import text_field %}'
        assert extract_template_references(source) == {"macros/forms.html"}

    def test_import_as(self):
        source = '{% import "macros/utils.html" as utils %}'
        assert extract_template_references(source) == {"macros/utils.html"}

    def test_multiple_references(self):
        source = (
            '{% extends "base.html" %}\n'
            '{% include "nav.html" %}\n'
            '{% from "macros.html" import btn %}\n'
        )
        assert extract_template_references(source) == {
            "base.html",
            "nav.html",
            "macros.html",
        }

    def test_single_quotes(self):
        source = "{% extends 'base.html' %}"
        assert extract_template_references(source) == {"base.html"}

    def test_whitespace_trimming_tags(self):
        source = '{%- extends "base.html" -%}'
        assert extract_template_references(source) == {"base.html"}

    def test_no_references(self):
        source = "<div>Hello</div>"
        assert extract_template_references(source) == set()

    def test_ignores_dynamic_variable(self):
        source = "{% include template_name %}"
        assert extract_template_references(source) == set()

    def test_resolves_relative_reference(self):
        assert resolve_template_reference("./_card.html", "pages/about.html") == "pages/_card.html"

    def test_resolves_parent_relative_reference(self):
        assert (
            resolve_template_reference("../shared/_card.html", "pages/about/index.html")
            == "pages/shared/_card.html"
        )

    def test_resolves_alias_reference(self):
        assert (
            resolve_template_reference(
                "@components/card.html",
                "pages/about.html",
                {"components": "ui/components"},
            )
            == "ui/components/card.html"
        )
