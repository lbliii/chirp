"""Middleware — Protocol-based, no inheritance required.

A middleware is any callable matching:
    async def mw(request: Request, next: Next) -> Response

Built-in middleware:
    CORSMiddleware -- Cross-Origin Resource Sharing
    StaticFiles -- Serve static files from a directory
    SessionMiddleware -- Signed cookie sessions (requires itsdangerous)
"""
