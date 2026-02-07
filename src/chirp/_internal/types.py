"""Shared type aliases used across chirp modules."""

from collections.abc import Callable
from typing import Any

# Route handler — user-defined function with variable signature
type Handler = Callable[..., Any]

# Error handler — receives (request, error?) and returns a response value
type ErrorHandler = Callable[..., Any]
