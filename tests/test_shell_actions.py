"""Tests for route-scoped shell action models."""

import pytest

from chirp.pages.shell_actions import ShellAction, ShellActions, ShellActionZone


def test_shell_action_form_requires_action() -> None:
    with pytest.raises(ValueError, match="form_action"):
        ShellActions(
            primary=ShellActionZone(
                items=(
                    ShellAction(
                        id="x",
                        label="y",
                        kind="form",
                        form_action="",
                    ),
                ),
            ),
        )


def test_shell_action_form_rejected_in_overflow() -> None:
    with pytest.raises(ValueError, match="overflow"):
        ShellActions(
            overflow=ShellActionZone(
                items=(
                    ShellAction(
                        id="x",
                        label="y",
                        kind="form",
                        form_action="/post",
                    ),
                ),
            ),
        )


def test_shell_action_link_rejects_form_fields() -> None:
    with pytest.raises(ValueError, match="form_action"):
        ShellActions(
            primary=ShellActionZone(
                items=(
                    ShellAction(
                        id="x",
                        label="y",
                        href="/z",
                        form_action="/oops",
                    ),
                ),
            ),
        )


def test_shell_action_form_accepts_attrs() -> None:
    """attrs on kind=form passes through to the <form> element (e.g. CSS custom properties)."""
    actions = ShellActions(
        primary=ShellActionZone(
            items=(
                ShellAction(
                    id="x",
                    label="y",
                    kind="form",
                    form_action="/a",
                    attrs='style="--color: red;"',
                ),
            ),
        ),
    )
    assert actions.primary.items[0].attrs == 'style="--color: red;"'


def test_shell_action_form_accepts_primary_zone() -> None:
    actions = ShellActions(
        primary=ShellActionZone(
            items=(
                ShellAction(
                    id="add",
                    label="Add",
                    kind="form",
                    form_action="/team/add",
                    hidden_fields=(("pokemon_id", "2"),),
                    hx_post="/team/add",
                    hx_target="#toast",
                    hx_swap="innerHTML",
                    hx_disinherit="hx-select",
                    submit_surface="shimmer",
                ),
            ),
        ),
    )
    assert actions.primary.items[0].kind == "form"
