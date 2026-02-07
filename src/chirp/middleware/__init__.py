"""Middleware — Protocol-based, no inheritance required.

A middleware is any callable matching:
    async def mw(request: Request, next: Next) -> Response
"""
