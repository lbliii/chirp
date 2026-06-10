"""Dangling-macro-CSS contract rule (#148 child 1).

``check_macro_css`` warns when a template imports core chirp macros
(``chirp/alpine.html`` / ``chirp/forms.html``) or literally emits one of their
dangling class names (``chirp-dropdown``, ``field--error``, ...) while chirp-ui
is not active, so the classes have no backing stylesheet.
"""

from chirp.contracts.rules_macro_css import check_macro_css
from chirp.contracts.types import Severity


class TestMacroCssRule:
    def test_core_macro_import_is_flagged_when_chirpui_inactive(self) -> None:
        sources = {
            "page.html": '{% from "chirp/alpine.html" import dropdown %}\n<div>{{ dropdown() }}</div>',
        }
        issues = check_macro_css(sources, chirpui_active=False)
        assert len(issues) == 1
        issue = issues[0]
        assert issue.severity == Severity.WARNING
        assert issue.category == "macro_css"
        assert issue.template == "page.html"
        assert "chirp-dropdown" in issue.message
        assert "use_chirp_ui(app)" in issue.message

    def test_forms_macro_import_is_flagged(self) -> None:
        sources = {
            "form.html": "{%- from 'chirp/forms.html' import field -%}\n{{ field() }}",
        }
        issues = check_macro_css(sources, chirpui_active=False)
        assert [i.category for i in issues] == ["macro_css"]
        assert issues[0].template == "form.html"

    def test_dangling_class_literal_is_flagged(self) -> None:
        sources = {
            "modal.html": '<div class="chirp-modal-content">hi</div>',
        }
        issues = check_macro_css(sources, chirpui_active=False)
        assert len(issues) == 1
        assert issues[0].category == "macro_css"

    def test_field_error_double_dash_class_is_flagged(self) -> None:
        sources = {
            "form.html": '<span class="field--error">bad</span>',
        }
        issues = check_macro_css(sources, chirpui_active=False)
        assert len(issues) == 1
        assert issues[0].template == "form.html"

    def test_silent_when_chirpui_active(self) -> None:
        # Negative control: same offending source, chirp-ui active -> backing CSS
        # is present, so the rule stays silent.
        sources = {
            "page.html": '{% from "chirp/alpine.html" import dropdown %}\n'
            '<div class="chirp-dropdown">{{ dropdown() }}</div>',
        }
        assert check_macro_css(sources, chirpui_active=True) == []

    def test_silent_for_clean_template(self) -> None:
        # Negative control: no core-macro import, no dangling class.
        sources = {
            "page.html": '<div class="card"><h1>Hello</h1></div>',
        }
        assert check_macro_css(sources, chirpui_active=False) == []

    def test_does_not_match_longer_class_token(self) -> None:
        # Negative control: an app's own ``chirp-dropdown-zone`` must NOT match
        # the ``chirp-dropdown`` token (word-boundary discipline).
        sources = {
            "page.html": '<div class="chirp-dropdown-zone">custom</div>',
        }
        assert check_macro_css(sources, chirpui_active=False) == []

    def test_framework_templates_are_skipped(self) -> None:
        # The macro source files themselves emit these classes; they must not
        # self-trigger.
        sources = {
            "chirp/alpine.html": '<div class="chirp-dropdown"></div>',
            "chirpui/modal.html": '<div class="chirp-modal-backdrop"></div>',
        }
        assert check_macro_css(sources, chirpui_active=False) == []

    def test_one_issue_per_offending_template(self) -> None:
        sources = {
            "a.html": '{% from "chirp/forms.html" import field %}',
            "b.html": '<div class="chirp-tabs"><span class="chirp-tab"></span></div>',
            "c.html": "<p>clean</p>",
        }
        issues = check_macro_css(sources, chirpui_active=False)
        assert {i.template for i in issues} == {"a.html", "b.html"}
