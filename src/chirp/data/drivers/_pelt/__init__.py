"""pelt — a pure-Python, free-threading-native PostgreSQL wire-protocol driver.

Developed in-tree as a private subpackage (``chirp.data.drivers._pelt``) behind the
``data-pg`` seam, and designed to be lifted out to a standalone ``bengal-pelt`` package once
mature (the seam then flips ``from . import _pelt`` → ``import pelt``). See the pelt saga
(GitHub #252) and ``.context/pelt-design-conventions.md``.

The E1 spine ships the sans-I/O core only: config + errors (public here), plus the internal
``_messages`` / ``_framing`` / ``_builder`` / ``_codecs`` primitives. Connection, pool,
transport, and auth land in later epics; the heavier of those (SCRAM, large codec tables, TLS)
will be lazy-imported via ``__getattr__`` so importing pelt stays cheap.

Part of the Bengal ecosystem:

    pounce      ASGI server        (serves apps)
    chirp       Web framework      (serves HTML)
    kida        Template engine    (renders HTML)
    patitas     Markdown parser    (parses content)
    rosettes    Syntax highlighter (highlights code)
    bengal      Static site gen    (builds sites)
    pelt        Postgres driver    (talks to the database)   <- this package
"""

# PEP 703: declare this module free-threading safe. pelt is pure Python and never re-enables
# the GIL on import; this marker keeps the whole stack's intent explicit and is the contract
# any future optional accelerator must also honor.
_Py_mod_gil = 0

from chirp.data.drivers._pelt.errors import (  # noqa: E402
    AuthenticationError,
    PeltConnectionError,
    PeltError,
    PeltTimeoutError,
    PostgresError,
    ProtocolError,
    TLSError,
)
from chirp.data.drivers._pelt.types import ConnectionConfig, PoolConfig  # noqa: E402

__all__ = [
    "AuthenticationError",
    "ConnectionConfig",
    "PeltConnectionError",
    "PeltError",
    "PeltTimeoutError",
    "PoolConfig",
    "PostgresError",
    "ProtocolError",
    "TLSError",
]
