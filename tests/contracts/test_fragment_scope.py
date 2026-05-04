"""Contract checks for fragment/block render scope hazards."""

from kida import DictLoader, Environment

from chirp.contracts.rules_fragment_scope import check_fragment_block_scope
from chirp.contracts.types import ContractIssue


def _check(source: str) -> list[ContractIssue]:
    env = Environment(
        loader=DictLoader(
            {
                "page.html": source,
                "surface.html": (
                    "{% def panel() %}<div>panel</div>{% end %}"
                    "{% def surface() %}<section>surface</section>{% end %}"
                ),
            }
        )
    )
    return check_fragment_block_scope({"page.html": source}, env)


def test_warns_when_fragment_block_uses_ancestor_import() -> None:
    issues = _check(
        """
{% block main %}
{% from "surface.html" import surface %}

{% block island_mount %}
  {% call surface() %}
    Island
  {% end %}
{% end %}
{% end %}
""",
    )

    issue = next(issue for issue in issues if issue.category == "fragment_scope")
    assert issue.severity.value == "warning"
    assert issue.template == "page.html"
    assert "Fragment block 'island_mount' references surface" in issue.message
    assert "block 'main'" in issue.message
    assert "template top level" in issue.message


def test_allows_fragment_block_with_top_level_import() -> None:
    issues = _check(
        """
{% from "surface.html" import surface %}

{% block main %}
{% block island_mount %}
  {% call surface() %}
    Island
  {% end %}
{% end %}
{% end %}
""",
    )

    assert all(issue.category != "fragment_scope" for issue in issues)


def test_allows_fragment_block_with_own_import() -> None:
    issues = _check(
        """
{% block main %}
{% block island_mount %}
  {% from "surface.html" import surface %}
  {% call surface() %}
    Island
  {% end %}
{% end %}
{% end %}
""",
    )

    assert all(issue.category != "fragment_scope" for issue in issues)


def test_warns_when_fragment_block_uses_ancestor_set_binding() -> None:
    issues = _check(
        """
{% block main %}
{% set label = "Ready" %}
{% block status %}{{ label }}{% end %}
{% end %}
""",
    )

    issue = next(issue for issue in issues if issue.category == "fragment_scope")
    assert "Fragment block 'status' references label" in issue.message
    assert "block 'main'" in issue.message


def test_pluralizes_multiple_ancestor_bindings() -> None:
    issues = _check(
        """
{% block main %}
{% from "surface.html" import panel, surface %}
{% block island_mount %}{{ panel() }}{{ surface() }}{% end %}
{% end %}
""",
    )

    issue = next(issue for issue in issues if issue.category == "fragment_scope")
    assert "panel, surface are defined inside block 'main'" in issue.message
