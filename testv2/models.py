from dataclasses import dataclass

from chirp.security.passwords import hash_password, verify_password


@dataclass(frozen=True, slots=True)
class User:
    id: str
    name: str
    password_hash: str
    is_authenticated: bool = True


_DEMO_HASH = hash_password("password")

USERS: dict[str, User] = {
    "admin": User(id="admin", name="Admin", password_hash=_DEMO_HASH),
}


async def load_user(user_id: str) -> User | None:
    return USERS.get(user_id)


def verify_user(username: str, password: str) -> User | None:
    user = USERS.get(username)
    if user and verify_password(password, user.password_hash):
        return user
    return None
