"""Framework-owned agent tool loop."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from chirp.ai._tool_calls import (
    format_tool_result,
    tool_result_message_anthropic,
    tool_result_message_openai,
)
from chirp.ai.errors import AIError
from chirp.ai.events import (
    DoneEvent,
    ErrorEvent,
    StreamEvent,
    StreamToolApprovalEvent,
    StreamToolCallEvent,
    StreamToolResultEvent,
    TokenEvent,
)
from chirp.ai.llm import LLM
from chirp.ai.memory import ConversationStore, InMemoryConversationStore, Message
from chirp.tools.approval import ToolApprovalStore
from chirp.tools.registry import ToolRegistry


class AgentRun:
    """Multi-round tool loop with optional conversation persistence."""

    __slots__ = (
        "_approval_store",
        "_llm",
        "_max_rounds",
        "_store",
        "_system",
        "_thread_id",
        "_tools",
    )

    def __init__(
        self,
        llm: LLM,
        tools: ToolRegistry,
        *,
        store: ConversationStore | None = None,
        approval_store: ToolApprovalStore | None = None,
        max_rounds: int = 10,
        system: str | None = None,
        thread_id: str = "default",
    ) -> None:
        self._llm = llm
        self._tools = tools
        self._store = store or InMemoryConversationStore()
        self._approval_store = approval_store
        self._max_rounds = max_rounds
        self._system = system
        self._thread_id = thread_id

    async def stream(
        self,
        user_message: str = "",
        *,
        append_user: bool = True,
        resume_approval_id: str | None = None,
    ) -> AsyncIterator[StreamEvent]:
        """Run tool rounds then stream the final assistant answer."""
        messages = await self._store.load(self._thread_id)
        if resume_approval_id is not None:
            async for event in self._resume_after_approval(messages, resume_approval_id):
                yield event
            return

        if append_user:
            if not user_message:
                msg = "user_message required when append_user=True"
                raise AIError(msg)
            user_msg: Message = {"role": "user", "content": user_message}
            messages = [*messages, user_msg]
            await self._store.append(self._thread_id, user_msg)

        try:
            for _ in range(self._max_rounds):
                completion = await self._llm.complete(
                    messages,
                    tools=self._tools,
                    system=self._system,
                )
                if not completion.tool_calls:
                    break

                await self._store.append(self._thread_id, completion.assistant_message)
                messages.append(completion.assistant_message)
                for call in completion.tool_calls:
                    tool_def = self._tools.get(call["name"])
                    if (
                        tool_def is not None
                        and tool_def.approval_required
                        and self._approval_store is not None
                    ):
                        approval = await self._approval_store.create(
                            thread_id=self._thread_id,
                            call_id=call["call_id"],
                            tool_name=call["name"],
                            arguments=call["arguments"],
                        )
                        yield StreamToolApprovalEvent(
                            approval_id=approval.approval_id,
                            call_id=call["call_id"],
                            name=call["name"],
                            arguments=call["arguments"],
                        )
                        return

                    async for event in self._dispatch_tool_call(messages, call):
                        yield event

            collected: list[str] = []
            async for event in self._llm.stream_events(
                messages,
                system=self._system,
            ):
                if isinstance(event, TokenEvent):
                    collected.append(event.text)
                yield event
                if isinstance(event, DoneEvent):
                    full = "".join(collected)
                    if full:
                        await self._store.append(
                            self._thread_id,
                            {"role": "assistant", "content": full},
                        )
                    return

        except AIError as exc:
            yield ErrorEvent(error=exc)
            raise

    async def _resume_after_approval(
        self,
        messages: list[Message],
        approval_id: str,
    ) -> AsyncIterator[StreamEvent]:
        if self._approval_store is None:
            msg = "resume_approval_id requires an approval_store"
            raise AIError(msg)

        approval = await self._approval_store.consume(approval_id)
        if approval is None:
            msg = f"Unknown or pending approval_id: {approval_id!r}"
            raise AIError(msg)

        call: dict[str, Any] = {
            "call_id": approval.call_id,
            "name": approval.tool_name,
            "arguments": approval.arguments,
        }

        if approval.status == "denied":
            result_str = "Error: tool call denied by user"
            yield StreamToolResultEvent(
                call_id=approval.call_id,
                result=None,
                error=result_str,
            )
            tool_msg = self._tool_result_message(approval.call_id, result_str)
            messages.append(tool_msg)
            await self._store.append(self._thread_id, tool_msg)
        else:
            async for event in self._dispatch_tool_call(
                messages,
                call,
                approval_granted=True,
            ):
                yield event

        for _ in range(self._max_rounds):
            completion = await self._llm.complete(
                messages,
                tools=self._tools,
                system=self._system,
            )
            if not completion.tool_calls:
                break

            await self._store.append(self._thread_id, completion.assistant_message)
            messages.append(completion.assistant_message)
            for next_call in completion.tool_calls:
                tool_def = self._tools.get(next_call["name"])
                if (
                    tool_def is not None
                    and tool_def.approval_required
                    and self._approval_store is not None
                ):
                    next_approval = await self._approval_store.create(
                        thread_id=self._thread_id,
                        call_id=next_call["call_id"],
                        tool_name=next_call["name"],
                        arguments=next_call["arguments"],
                    )
                    yield StreamToolApprovalEvent(
                        approval_id=next_approval.approval_id,
                        call_id=next_call["call_id"],
                        name=next_call["name"],
                        arguments=next_call["arguments"],
                    )
                    return

                async for event in self._dispatch_tool_call(messages, next_call):
                    yield event

        collected: list[str] = []
        async for event in self._llm.stream_events(
            messages,
            system=self._system,
        ):
            if isinstance(event, TokenEvent):
                collected.append(event.text)
            yield event
            if isinstance(event, DoneEvent):
                full = "".join(collected)
                if full:
                    await self._store.append(
                        self._thread_id,
                        {"role": "assistant", "content": full},
                    )
                return

    async def _dispatch_tool_call(
        self,
        messages: list[Message],
        call: dict[str, Any],
        *,
        approval_granted: bool = False,
    ) -> AsyncIterator[StreamEvent]:
        call_id = str(call["call_id"])
        name = str(call["name"])
        arguments: dict[str, Any] = dict(call["arguments"])
        yield StreamToolCallEvent(
            call_id=call_id,
            name=name,
            arguments=arguments,
        )
        try:
            result = await self._tools.call_tool(
                name,
                arguments,
                approval_granted=approval_granted,
            )
            result_str = format_tool_result(result)
            error: str | None = None
        except Exception as exc:
            result = None
            result_str = f"Error: {exc}"
            error = str(exc)
        yield StreamToolResultEvent(
            call_id=call_id,
            result=result,
            error=error,
        )
        tool_msg = self._tool_result_message(call_id, result_str)
        messages.append(tool_msg)
        await self._store.append(self._thread_id, tool_msg)

    def _tool_result_message(self, call_id: str, content: str) -> Message:
        if self._llm.provider == "anthropic":
            return tool_result_message_anthropic(call_id, content)
        return tool_result_message_openai(call_id, content)
