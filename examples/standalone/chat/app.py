"""Chat Room — real-time multi-user chat via SSE + POST.

The idiomatic chirp pattern for bidirectional communication: POST to
send messages, Server-Sent Events to receive them.  No WebSocket, no
special infrastructure — just plain HTTP.

Demonstrates:
- Pub-sub broadcast via ChatBus (asyncio.Queue per subscriber)
- SSE + POST for bidirectional communication
- Fragment rendering for live HTML updates
- Session-based usernames
- Thread-safe message history

Run:
    python app.py
"""

import asyncio
import contextlib
import os
import threading
import time
from collections import deque
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path

from chirp import App, AppConfig, EventStream, Fragment, Redirect, Request, Template
from chirp.middleware.sessions import SessionConfig, SessionMiddleware, get_session

TEMPLATES_DIR = Path(__file__).parent / "templates"

_secret = os.environ.get("SESSION_SECRET_KEY", "dev-only-not-for-production")

config = AppConfig(template_dir=TEMPLATES_DIR, workers=1, worker_mode="async")
app = App(config=config)
app.add_middleware(SessionMiddleware(SessionConfig(secret_key=_secret)))

# ---------------------------------------------------------------------------
# Chat message model
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ChatMessage:
    """A single chat message — immutable, safe to broadcast."""

    username: str
    text: str
    timestamp: float


_ChatSub = tuple[asyncio.Queue[ChatMessage | None], asyncio.AbstractEventLoop]


# ---------------------------------------------------------------------------
# ChatBus — async broadcast modeled on ToolEventBus
# ---------------------------------------------------------------------------


class ChatBus:
    """Async broadcast channel for chat messages.

    Each call to ``subscribe()`` returns an async iterator backed by its
    own ``asyncio.Queue``.  When ``emit()`` is called, the message is
    placed into every active subscriber's queue.

    Thread-safe: the subscriber set is protected by a Lock, and cross-thread
    emitters hand queue mutation back to each subscriber's event loop.
    """

    __slots__ = ("_lock", "_subscribers")

    def __init__(self) -> None:
        self._subscribers: set[_ChatSub] = set()
        self._lock = threading.Lock()

    async def emit(self, message: ChatMessage) -> None:
        """Broadcast a message to all active subscribers."""
        with self._lock:
            subscribers = set(self._subscribers)
        for queue, loop in subscribers:
            self._schedule_message(loop, queue, message)

    def _schedule_message(
        self,
        loop: asyncio.AbstractEventLoop,
        queue: asyncio.Queue[ChatMessage | None],
        message: ChatMessage,
    ) -> None:
        try:
            running_loop = asyncio.get_running_loop()
        except RuntimeError:
            running_loop = None
        if running_loop is loop:
            self._deliver_message(queue, message)
            return
        with contextlib.suppress(RuntimeError):
            loop.call_soon_threadsafe(self._deliver_message, queue, message)

    def _deliver_message(
        self,
        queue: asyncio.Queue[ChatMessage | None],
        message: ChatMessage,
    ) -> None:
        with contextlib.suppress(asyncio.QueueFull):
            queue.put_nowait(message)

    async def subscribe(self) -> AsyncIterator[ChatMessage]:
        """Subscribe to chat messages.

        Returns an async iterator that yields messages as they arrive.
        Cleaned up automatically when the iterator exits.
        """
        queue: asyncio.Queue[ChatMessage | None] = asyncio.Queue(maxsize=256)
        loop = asyncio.get_running_loop()
        sub: _ChatSub = (queue, loop)
        with self._lock:
            self._subscribers.add(sub)
        try:
            while True:
                message = await queue.get()
                if message is None:
                    break
                yield message
        finally:
            with self._lock:
                self._subscribers.discard(sub)


_bus = ChatBus()

# ---------------------------------------------------------------------------
# Message history — thread-safe bounded deque
# ---------------------------------------------------------------------------

_history: deque[ChatMessage] = deque(maxlen=50)
_history_lock = threading.Lock()


def _add_message(msg: ChatMessage) -> None:
    with _history_lock:
        _history.append(msg)


def _get_history() -> list[ChatMessage]:
    with _history_lock:
        return list(_history)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.route("/")
def index():
    """Redirect to chat or login depending on session state."""
    session = get_session()
    if session.get("username"):
        return Redirect("/chat")
    return Redirect("/login")


@app.route("/login")
def login_page():
    """Show the username entry form."""
    return Template("login.html")


@app.route("/login", methods=["POST"])
async def do_login(request: Request):
    """Set the session username and redirect to chat."""
    form = await request.form()
    username = (form.get("username") or "").strip()
    if not username:
        return Template("login.html", error="Username is required")
    session = get_session()
    session["username"] = username
    return Redirect("/chat")


@app.route("/logout", methods=["POST"])
def logout():
    """Clear the session and redirect to login."""
    session = get_session()
    session.clear()
    return Redirect("/login")


@app.route("/chat")
def chat_page():
    """Full chat page with message history and SSE connection."""
    session = get_session()
    username = session.get("username")
    if not username:
        return Redirect("/login")
    messages = _get_history()
    return Template("chat.html", messages=messages, username=username)


@app.route("/chat/send", methods=["POST"], name="chat.send")
async def send_message(request: Request):
    """Submit a message — broadcast via ChatBus, return 204."""
    session = get_session()
    username = session.get("username")
    if not username:
        return ("Unauthorized", 401)

    form = await request.form()
    text = (form.get("message") or "").strip()
    if not text:
        return ("", 204)

    msg = ChatMessage(username=username, text=text, timestamp=time.time())
    _add_message(msg)
    await _bus.emit(msg)
    return ("", 204)


@app.route("/chat/events", referenced=True)
def chat_events():
    """SSE endpoint — stream new messages as rendered HTML fragments."""

    async def generate():
        async for message in _bus.subscribe():
            yield Fragment(
                "chat.html",
                "message",
                msg=message,
            )

    return EventStream(generate())


if __name__ == "__main__":
    app.run()
