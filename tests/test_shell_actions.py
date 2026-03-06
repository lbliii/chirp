"""Tests for route-scoped shell action models and context cascade."""

import pytest

from chirp.pages.context import build_cascade_context
from chirp.pages.shell_actions import (
    ShellAction,
    ShellActions,
    ShellActionZone,
    merge_shell_actions,
    shell_actions_fragment,
)
from chirp.pages.types import ContextProvider


class TestShellActionMerging:
    def test_merge_overrides_and_removes_by_id(self) -> None:
        parent = ShellActions(
            primary=ShellActionZone(
                items=(
                    ShellAction(id="new-thread", label="New thread", href="/threads/new"),
                    ShellAction(id="follow", label="Follow", action="follow"),
                )
            )
        )
        child = ShellActions(
            primary=ShellActionZone(
                items=(ShellAction(id="reply", label="Reply", href="/threads/1/reply"),),
                remove=("new-thread",),
            ),
            controls=ShellActionZone(
                items=(ShellAction(id="sort", label="Sort", action="sort"),),
            ),
        )

        merged = merge_shell_actions(parent, child)

        assert merged is not None
        assert [item.id for item in merged.primary.items] == ["follow", "reply"]
        assert [item.id for item in merged.controls.items] == ["sort"]

    def test_merge_replaces_zone(self) -> None:
        parent = ShellActions(
            overflow=ShellActionZone(
                items=(ShellAction(id="archive", label="Archive", action="archive"),)
            )
        )
        child = ShellActions(
            overflow=ShellActionZone(
                items=(ShellAction(id="delete", label="Delete", action="delete"),),
                mode="replace",
            )
        )

        merged = merge_shell_actions(parent, child)

        assert merged is not None
        assert [item.id for item in merged.overflow.items] == ["delete"]

    def test_empty_replace_still_represents_a_clear(self) -> None:
        parent = ShellActions(
            primary=ShellActionZone(
                items=(ShellAction(id="new-thread", label="New thread", href="/threads/new"),)
            )
        )
        child = ShellActions(primary=ShellActionZone(mode="replace"))

        merged = merge_shell_actions(parent, child)

        assert merged is not None
        assert merged.has_items is False
        assert shell_actions_fragment(merged) is not None

    def test_duplicate_ids_raise(self) -> None:
        with pytest.raises(ValueError, match="Duplicate shell action id"):
            ShellActions(
                primary=ShellActionZone(
                    items=(
                        ShellAction(id="duplicate", label="One", href="/a"),
                        ShellAction(id="duplicate", label="Two", href="/b"),
                    )
                )
            )


class TestBuildCascadeContext:
    @pytest.mark.asyncio
    async def test_shell_actions_merge_across_context_providers(self) -> None:
        def root_context() -> dict[str, object]:
            return {
                "shell_actions": ShellActions(
                    primary=ShellActionZone(
                        items=(ShellAction(id="new-thread", label="New thread", href="/threads/new"),)
                    )
                ),
                "title": "Forum",
            }

        def thread_context(shell_actions: ShellActions) -> dict[str, object]:
            assert [item.id for item in shell_actions.primary.items] == ["new-thread"]
            return {
                "shell_actions": ShellActions(
                    primary=ShellActionZone(
                        items=(ShellAction(id="reply", label="Reply", href="/threads/1/reply"),),
                        remove=("new-thread",),
                    )
                ),
                "title": "Thread",
            }

        providers = (
            ContextProvider(module_path="root", func=root_context, depth=0),
            ContextProvider(module_path="thread", func=thread_context, depth=1),
        )

        ctx = await build_cascade_context(providers, path_params={})

        assert ctx["title"] == "Thread"
        shell_actions = ctx["shell_actions"]
        assert isinstance(shell_actions, ShellActions)
        assert [item.id for item in shell_actions.primary.items] == ["reply"]
