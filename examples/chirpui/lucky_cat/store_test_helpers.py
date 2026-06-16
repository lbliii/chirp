"""Test helpers for session-scoped store assertions (#285)."""

from collections.abc import Iterator
from contextlib import contextmanager

import session_store


@contextmanager
def sole_client_store() -> Iterator[None]:
    """Bind store accessors to the active client session bucket."""
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
