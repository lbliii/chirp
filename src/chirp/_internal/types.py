"""Shared type aliases used across chirp modules."""

from collections.abc import Callable
from typing import Any, TypeAlias

# Route handler — user-defined function with variable signature
Handler: TypeAlias = Callable[..., Any]

# Error handler — receives (request, error?) and returns a response value
ErrorHandler: TypeAlias = Callable[..., Any]
