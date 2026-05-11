`_actions.py` dispatch now passes the current `Request` into action functions and request-aware `app.provide()` factories, preserving request-scoped service context for filesystem actions.
