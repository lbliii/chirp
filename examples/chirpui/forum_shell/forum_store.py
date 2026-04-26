"""Tiny in-memory forum store for the forum_shell example."""

import threading
from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class Character:
    id: int
    name: str
    player: str


@dataclass(frozen=True, slots=True)
class Post:
    id: int
    character_id: int
    body: str
    mention_ids: tuple[int, ...] = ()


@dataclass(frozen=True, slots=True)
class Thread:
    slug: str
    title: str
    board_slug: str
    participant_ids: tuple[int, ...]
    posts: tuple[Post, ...] = field(default_factory=tuple)
    unread: int = 0


@dataclass(frozen=True, slots=True)
class Board:
    slug: str
    name: str
    description: str


class ForumStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.reset()

    def reset(self) -> None:
        with self._lock:
            self._boards = (
                Board("announcements", "Announcements", "World news, staff notes, and events."),
                Board("ic", "In Character", "Play-by-post scenes and active story threads."),
            )
            self._characters = (
                Character(1, "Mara Vale", "Lawrence"),
                Character(2, "Theo Ash", "Rowan"),
                Character(3, "Juniper Cross", "Mina"),
            )
            self._threads = {
                "welcome": Thread(
                    slug="welcome",
                    title="Welcome to the Observatory",
                    board_slug="announcements",
                    participant_ids=(1, 2),
                    posts=(Post(1, 1, "Welcome in. Claim a face, say hello, and start plotting."),),
                    unread=2,
                ),
                "market-rain": Thread(
                    slug="market-rain",
                    title="Rain over the night market",
                    board_slug="ic",
                    participant_ids=(1, 3),
                    posts=(
                        Post(1, 3, "Juniper waits beneath the awning, watching lanterns blur."),
                        Post(2, 1, "Mara arrives late, carrying coffee and bad news.", (3,)),
                    ),
                    unread=5,
                ),
            }

    def boards(self) -> tuple[Board, ...]:
        with self._lock:
            return self._boards

    def characters(self) -> tuple[Character, ...]:
        with self._lock:
            return self._characters

    def board(self, slug: str) -> Board | None:
        with self._lock:
            return next((board for board in self._boards if board.slug == slug), None)

    def board_threads(self, board_slug: str) -> tuple[Thread, ...]:
        with self._lock:
            return tuple(
                thread for thread in self._threads.values() if thread.board_slug == board_slug
            )

    def thread(self, slug: str) -> Thread | None:
        with self._lock:
            return self._threads.get(slug)

    def reply(
        self,
        thread_slug: str,
        *,
        character_id: int,
        body: str,
        mention_ids: list[int],
    ) -> Thread | None:
        with self._lock:
            thread = self._threads.get(thread_slug)
            if thread is None:
                return None
            post = Post(
                id=len(thread.posts) + 1,
                character_id=character_id,
                body=body,
                mention_ids=tuple(mention_ids),
            )
            updated = Thread(
                slug=thread.slug,
                title=thread.title,
                board_slug=thread.board_slug,
                participant_ids=tuple(
                    sorted({*thread.participant_ids, character_id, *mention_ids})
                ),
                posts=(*thread.posts, post),
                unread=thread.unread + 1,
            )
            self._threads[thread_slug] = updated
            return updated

    def unread_count(self) -> int:
        with self._lock:
            return sum(thread.unread for thread in self._threads.values())

    def character_name(self, character_id: int) -> str:
        with self._lock:
            character = next((c for c in self._characters if c.id == character_id), None)
            return character.name if character is not None else "Unknown"

    def mentionables(self, query: str) -> list[dict[str, object]]:
        normalized = query.casefold().strip()
        with self._lock:
            characters = self._characters
        matches = [
            character
            for character in characters
            if not normalized
            or normalized in character.name.casefold()
            or normalized in character.player.casefold()
        ]
        return [
            {"id": character.id, "label": character.name, "detail": character.player}
            for character in matches
        ]


store = ForumStore()


def reset_store() -> None:
    store.reset()
