"""Tests for chirp.shell_regions stable ids."""

from chirp.shell_actions import SHELL_ACTIONS_TARGET as FROM_ACTIONS
from chirp.shell_regions import (
    DOCUMENT_TITLE_ELEMENT_ID,
    SHELL_ACTIONS_TARGET,
    SHELL_ELEMENT_IDS,
)


def test_shell_actions_target_matches_shell_actions_module() -> None:
    assert SHELL_ACTIONS_TARGET == FROM_ACTIONS == "chirp-shell-actions"


def test_document_title_id() -> None:
    assert DOCUMENT_TITLE_ELEMENT_ID == "chirpui-document-title"


def test_shell_element_ids_frozen() -> None:
    assert len(SHELL_ELEMENT_IDS) == 2
    assert DOCUMENT_TITLE_ELEMENT_ID in SHELL_ELEMENT_IDS
    assert SHELL_ACTIONS_TARGET in SHELL_ELEMENT_IDS
