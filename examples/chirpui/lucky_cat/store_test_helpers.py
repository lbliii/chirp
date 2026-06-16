"""Test helpers for session-scoped store assertions (#285)."""

from collections.abc import Iterator
from contextlib import contextmanager


@contextmanager
def sole_client_store() -> Iterator[None]:
    """Bind store accessors to the active client session bucket.

    ``session_store`` is imported lazily (not at module scope) on purpose: the
    example harness purges and re-imports each example's sibling modules per
    test (see ``examples/conftest.py``). A module-level import here would bind
    the instance present at *collection* time, which a sibling example's purge
    can evict — leaving this helper reading a stale, empty registry while the
    app under test mutates a freshly re-imported one. Resolving it at call time
    guarantees the helper and the app share the same ``session_store`` module.
    """
    import session_store

    key = session_store.active_store_key()
    with session_store.bind(key):
        yield


def client_balance() -> int:
    import wallet

    with sole_client_store():
        return wallet.balance()


async def warm_authed_store(client, cookie: str, *, cookie_name: str) -> None:
    """Establish the session store bucket via a signed-in page render."""
    await client.get("/", headers={"Cookie": f"{cookie_name}={cookie}"})
