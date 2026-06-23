"""Conversation memory for agent loops."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

Message = dict[str, Any]


@runtime_checkable
class ConversationStore(Protocol):
    """Load/append provider-neutral chat messages by thread key."""

    async def load(self, key: str) -> list[Message]: ...

    async def append(self, key: str, message: Message) -> None: ...

    async def clear(self, key: str) -> None: ...


class InMemoryConversationStore:
    """Process-local store for demos and tests."""

    __slots__ = ("_threads",)

    def __init__(self) -> None:
        self._threads: dict[str, list[Message]] = {}

    async def load(self, key: str) -> list[Message]:
        return list(self._threads.get(key, []))

    async def append(self, key: str, message: Message) -> None:
        self._threads.setdefault(key, []).append(dict(message))

    async def clear(self, key: str) -> None:
        self._threads.pop(key, None)


class SessionConversationStore:
    """Persist messages in the server session under ``chirp_ai_thread``."""

    __slots__ = ("_session_key",)

    def __init__(self, session_key: str = "chirp_ai_messages") -> None:
        self._session_key = session_key

    async def load(self, key: str) -> list[Message]:
        from chirp.middleware.session import get_session

        session = get_session()
        threads = session.get(self._session_key) or {}
        return list(threads.get(key, []))

    async def append(self, key: str, message: Message) -> None:
        from chirp.middleware.session import get_session

        session = get_session()
        threads = dict(session.get(self._session_key) or {})
        thread = list(threads.get(key, []))
        thread.append(dict(message))
        threads[key] = thread
        session[self._session_key] = threads

    async def clear(self, key: str) -> None:
        from chirp.middleware.session import get_session

        session = get_session()
        threads = dict(session.get(self._session_key) or {})
        threads.pop(key, None)
        session[self._session_key] = threads
