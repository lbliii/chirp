"""Framework-owned agent tool loop."""

from __future__ import annotations

from collections.abc import AsyncIterator

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
    StreamToolCallEvent,
    StreamToolResultEvent,
    TokenEvent,
)
from chirp.ai.llm import LLM
from chirp.ai.memory import ConversationStore, InMemoryConversationStore, Message
from chirp.tools.registry import ToolRegistry


class AgentRun:
    """Multi-round tool loop with optional conversation persistence."""

    __slots__ = ("_llm", "_max_rounds", "_store", "_system", "_thread_id", "_tools")

    def __init__(
        self,
        llm: LLM,
        tools: ToolRegistry,
        *,
        store: ConversationStore | None = None,
        max_rounds: int = 10,
        system: str | None = None,
        thread_id: str = "default",
    ) -> None:
        self._llm = llm
        self._tools = tools
        self._store = store or InMemoryConversationStore()
        self._max_rounds = max_rounds
        self._system = system
        self._thread_id = thread_id

    async def stream(
        self,
        user_message: str = "",
        *,
        append_user: bool = True,
    ) -> AsyncIterator[StreamEvent]:
        """Run tool rounds then stream the final assistant answer."""
        messages = await self._store.load(self._thread_id)
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
                    yield StreamToolCallEvent(
                        call_id=call["call_id"],
                        name=call["name"],
                        arguments=call["arguments"],
                    )
                    try:
                        result = await self._tools.call_tool(call["name"], call["arguments"])
                        result_str = format_tool_result(result)
                        error: str | None = None
                    except Exception as exc:
                        result = None
                        result_str = f"Error: {exc}"
                        error = str(exc)
                    yield StreamToolResultEvent(
                        call_id=call["call_id"],
                        result=result,
                        error=error,
                    )
                    tool_msg = self._tool_result_message(call["call_id"], result_str)
                    messages.append(tool_msg)
                    await self._store.append(self._thread_id, tool_msg)

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

    def _tool_result_message(self, call_id: str, content: str) -> Message:
        if self._llm.provider == "anthropic":
            return tool_result_message_anthropic(call_id, content)
        return tool_result_message_openai(call_id, content)
