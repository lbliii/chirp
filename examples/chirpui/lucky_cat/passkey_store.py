"""In-memory passkey credential store for Lucky Cat's demo account.

Follows the same store convention as ``users.py`` / ``wallet.py``: frozen rows,
module-level state behind a ``threading.Lock``, ``reset()`` for test isolation.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass

from chirp.security.passkeys import RegisteredCredential


@dataclass(frozen=True, slots=True)
class StoredPasskey:
    """Persisted passkey row — satisfies :class:`~chirp.security.passkeys.PasskeyCredential`."""

    credential_id: bytes
    public_key: bytes
    sign_count: int
    user_id: str
    nickname: str = ""


_lock = threading.Lock()
_by_id: dict[bytes, StoredPasskey] = {}
_by_user: dict[str, list[bytes]] = {}


def reset() -> None:
    global _by_id, _by_user
    with _lock:
        _by_id = {}
        _by_user = {}


def save(user_id: str, registered: RegisteredCredential, *, nickname: str = "") -> StoredPasskey:
    row = StoredPasskey(
        credential_id=registered.credential_id,
        public_key=registered.public_key,
        sign_count=registered.sign_count,
        user_id=user_id,
        nickname=nickname or "Passkey",
    )
    with _lock:
        _by_id[row.credential_id] = row
        ids = _by_user.setdefault(user_id, [])
        if row.credential_id not in ids:
            ids.append(row.credential_id)
    return row


def get(credential_id: bytes) -> StoredPasskey | None:
    with _lock:
        return _by_id.get(credential_id)


def list_for_user(user_id: str) -> list[StoredPasskey]:
    with _lock:
        return [_by_id[cid] for cid in _by_user.get(user_id, []) if cid in _by_id]


def all_credential_ids() -> list[bytes]:
    with _lock:
        return list(_by_id.keys())


def update_sign_count(credential_id: bytes, new_sign_count: int) -> None:
    with _lock:
        row = _by_id.get(credential_id)
        if row is None:
            return
        _by_id[credential_id] = StoredPasskey(
            credential_id=row.credential_id,
            public_key=row.public_key,
            sign_count=new_sign_count,
            user_id=row.user_id,
            nickname=row.nickname,
        )


def seed(row: StoredPasskey) -> None:
    with _lock:
        _by_id[row.credential_id] = row
        ids = _by_user.setdefault(row.user_id, [])
        if row.credential_id not in ids:
            ids.append(row.credential_id)
