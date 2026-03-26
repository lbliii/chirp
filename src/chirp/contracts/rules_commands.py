"""Invoker Commands validation — commandfor/command attribute checks.

The Invoker Commands API (baseline Jan 2026) enables declarative element
relationships::

    <button commandfor="my-dialog" command="show-modal">Open</button>
    <dialog id="my-dialog">...</dialog>

``check_commandfor_targets`` validates that ``commandfor`` attribute values
reference existing element IDs, similar to how ``check_hx_target_selectors``
validates ``hx-target`` selectors.

``check_command_values`` validates that ``command`` attributes use recognized
built-in commands (or valid custom ``--prefixed`` commands).
"""

import re

from .types import ContractIssue, Severity
from .utils import closest_id

# Built-in commands from the Invoker Commands spec
_BUILTIN_COMMANDS = frozenset(
    {
        # Dialog commands
        "show-modal",
        "close",
        # Popover commands
        "toggle-popover",
        "show-popover",
        "hide-popover",
        # Fullscreen
        "request-fullscreen",
        # Clipboard
        "copy",
        "cut",
        "paste",
    }
)

_COMMANDFOR_PATTERN = re.compile(r'(?<![-\w])commandfor\b\s*=\s*(["\'])(.*?)\1')
_COMMAND_PATTERN = re.compile(r'(?<![-\w])command\b\s*=\s*(["\'])(.*?)\1')


def check_commandfor_targets(
    template_sources: dict[str, str],
    all_ids: set[str],
) -> tuple[list[ContractIssue], int]:
    """Validate commandfor attribute values reference existing element IDs.

    Returns ``(issues, validated_count)`` like ``check_hx_target_selectors``.
    """
    issues: list[ContractIssue] = []
    validated = 0
    for template_name, source in template_sources.items():
        if template_name.startswith(("chirp/", "chirpui/")):
            continue
        for match in _COMMANDFOR_PATTERN.finditer(source):
            target_id = match.group(2).strip()
            if not target_id or "{{" in target_id or "{%" in target_id:
                continue
            validated += 1
            if target_id not in all_ids:
                suggestion = closest_id(target_id, all_ids)
                hint = f' Did you mean "{suggestion}"?' if suggestion else ""
                issues.append(
                    ContractIssue(
                        severity=Severity.WARNING,
                        category="commandfor",
                        message=(
                            f'commandfor="{target_id}" — no element with '
                            f'id="{target_id}" found in any template.{hint}'
                        ),
                        template=template_name,
                        details=(
                            f"Available IDs: {', '.join(sorted(all_ids)[:10])}" if all_ids else None
                        ),
                    )
                )
    return issues, validated


def check_command_values(
    template_sources: dict[str, str],
) -> list[ContractIssue]:
    """Validate command attribute values are recognized built-in or valid custom commands.

    Custom commands must use the ``--prefix`` convention (e.g., ``--my-action``).
    """
    issues: list[ContractIssue] = []
    for template_name, source in template_sources.items():
        if template_name.startswith(("chirp/", "chirpui/")):
            continue
        for match in _COMMAND_PATTERN.finditer(source):
            value = match.group(2).strip().lower()
            if not value or "{{" in value or "{%" in value:
                continue
            # Custom commands use -- prefix
            if value.startswith("--"):
                continue
            if value not in _BUILTIN_COMMANDS:
                issues.append(
                    ContractIssue(
                        severity=Severity.WARNING,
                        category="command",
                        message=(
                            f'command="{match.group(2)}" — not a recognized '
                            f"built-in command. Built-in commands: "
                            f"{', '.join(sorted(_BUILTIN_COMMANDS))}. "
                            f"Custom commands should use the --prefix convention."
                        ),
                        template=template_name,
                    )
                )
    return issues
