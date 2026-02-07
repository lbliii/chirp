"""Chirp application class.

Mutable during setup (route registration, middleware, filters).
Frozen at runtime when app.run() or __call__() is first invoked.
"""
