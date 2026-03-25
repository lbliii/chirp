"""Tests for Invoker Commands (commandfor/command) validation."""

from chirp.contracts.rules_commands import check_command_values, check_commandfor_targets
from chirp.contracts.types import Severity


class TestCommandforTargets:
    """Validate commandfor targets reference existing IDs."""

    def test_valid_target(self):
        sources = {
            "page.html": (
                '<button commandfor="my-dialog" command="show-modal">Open</button>'
                '<dialog id="my-dialog"><p>Hello</p></dialog>'
            ),
        }
        issues, validated = check_commandfor_targets(sources, {"my-dialog"})
        assert issues == []
        assert validated == 1

    def test_missing_target(self):
        sources = {
            "page.html": '<button commandfor="missing-dialog" command="show-modal">Open</button>',
        }
        issues, validated = check_commandfor_targets(sources, {"other-dialog"})
        assert len(issues) == 1
        assert issues[0].severity == Severity.WARNING
        assert issues[0].category == "commandfor"
        assert "missing-dialog" in issues[0].message
        assert validated == 1

    def test_fuzzy_suggestion(self):
        sources = {
            "page.html": '<button commandfor="my-dialg" command="show-modal">Open</button>',
        }
        issues, _ = check_commandfor_targets(sources, {"my-dialog"})
        assert len(issues) == 1
        assert "my-dialog" in issues[0].message

    def test_skips_dynamic_values(self):
        sources = {
            "page.html": (
                '<button commandfor="{{ dialog_id }}" command="show-modal">Open</button>'
            ),
        }
        issues, validated = check_commandfor_targets(sources, set())
        assert issues == []
        assert validated == 0

    def test_skips_builtin_templates(self):
        sources = {
            "chirp/devtools.html": (
                '<button commandfor="missing" command="show-modal">Open</button>'
            ),
        }
        issues, validated = check_commandfor_targets(sources, set())
        assert issues == []
        assert validated == 0


class TestCommandValues:
    """Validate command attribute values."""

    def test_builtin_commands_pass(self):
        sources = {
            "page.html": (
                '<button command="show-modal">Open</button>'
                '<button command="close">Close</button>'
                '<button command="toggle-popover">Toggle</button>'
            ),
        }
        issues = check_command_values(sources)
        assert issues == []

    def test_custom_prefixed_commands_pass(self):
        sources = {
            "page.html": '<button command="--my-custom-action">Go</button>',
        }
        issues = check_command_values(sources)
        assert issues == []

    def test_unknown_command_warns(self):
        sources = {
            "page.html": '<button command="do-something">Go</button>',
        }
        issues = check_command_values(sources)
        assert len(issues) == 1
        assert issues[0].severity == Severity.WARNING
        assert issues[0].category == "command"
        assert "do-something" in issues[0].message

    def test_skips_dynamic_values(self):
        sources = {
            "page.html": '<button command="{{ cmd }}">Go</button>',
        }
        issues = check_command_values(sources)
        assert issues == []

    def test_skips_builtin_templates(self):
        sources = {
            "chirpui/toolbar.html": '<button command="invalid">Go</button>',
        }
        issues = check_command_values(sources)
        assert issues == []
