"""Tests for unreachable filesystem page block detection."""

from __future__ import annotations

from kida import DictLoader, Environment

from chirp.contracts.rules_unreachable_blocks import check_unreachable_blocks
from chirp.contracts.types import Severity


def _env(templates: dict[str, str]) -> Environment:
    return Environment(loader=DictLoader(templates))


def test_warns_on_sibling_page_scripts() -> None:
    env = _env(
        {
            "page.html": """
{% block page_root %}
  {% block page_content %}<p>hi</p>{% end %}
{% end %}
{% block page_scripts %}
<script>console.log(1)</script>
{% end %}
"""
        }
    )
    issues = check_unreachable_blocks({"page.html"}, env)
    assert len(issues) == 1
    assert issues[0].category == "unreachable_block"
    assert issues[0].severity == Severity.WARNING
    assert "page_scripts" in issues[0].message


def test_no_warning_when_nested_under_page_root() -> None:
    env = _env(
        {
            "page.html": """
{% block page_root %}
  {% block page_content %}
    {% block inner %}x{% end %}
  {% end %}
{% end %}
"""
        }
    )
    issues = check_unreachable_blocks({"page.html"}, env)
    assert issues == []


def test_skips_template_that_extends() -> None:
    env = _env(
        {
            "base.html": "{% block content %}{% end %}",
            "page.html": """{% extends "base.html" %}
{% block content %}{% end %}
{% block extra %}{% end %}
""",
        }
    )
    issues = check_unreachable_blocks({"page.html"}, env)
    assert issues == []


def test_empty_page_leaf_set() -> None:
    env = _env({"page.html": "{% block page_root %}{% end %}"})
    assert check_unreachable_blocks(set(), env) == []


def test_kida_env_none() -> None:
    assert check_unreachable_blocks({"page.html"}, None) == []


def test_composition_roots_extra() -> None:
    env = _env(
        {
            "page.html": """
{% block page_root %}{% end %}
{% block sidebar %}{% end %}
"""
        }
    )
    issues = check_unreachable_blocks(
        {"page.html"},
        env,
        extras={"composition_roots": {"sidebar"}},
    )
    assert issues == []
