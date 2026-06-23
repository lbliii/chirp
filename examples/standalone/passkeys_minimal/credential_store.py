"""In-memory passkey credential store — BYO row for the minimal example."""

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
    """Clear all credentials (test isolation)."""
    global _by_id, _by_user
    with _lock:
        _by_id = {}
        _by_user = {}


def save(user_id: str, registered: RegisteredCredential, *, nickname: str = "") -> StoredPasskey:
    """Persist a verified registration result."""
    row = StoredPasskey(
        credential_id=registered.credential_id,
        public_key=registered.public_key,
        sign_count=registered.sign_count,
        user_id=user_id,
        nickname=nickname,
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


def delete(credential_id: bytes, *, user_id: str) -> bool:
    with _lock:
        row = _by_id.pop(credential_id, None)
        if row is None or row.user_id != user_id:
            if row is not None:
                _by_id[credential_id] = row
            return False
        ids = _by_user.get(user_id, [])
        if credential_id in ids:
            ids.remove(credential_id)
        return True


def seed(row: StoredPasskey) -> None:
    """Insert a row directly (TestClient ceremony tests)."""
    with _lock:
        _by_id[row.credential_id] = row
        ids = _by_user.setdefault(row.user_id, [])
        if row.credential_id not in ids:
            ids.append(row.credential_id)
