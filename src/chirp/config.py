"""Application configuration.

AppConfig is a frozen dataclass — immutable after creation, IDE-autocompletable,
no string-key dict lookups.
"""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class AppConfig:
    """Application configuration. Immutable after creation.

    All fields have sensible defaults. Override what you need::

        config = AppConfig(debug=True, port=3000, secret_key="s3cr3t")
    """

    # Server
    host: str = "127.0.0.1"
    port: int = 8000
    debug: bool = False

    # Reload (development mode — requires debug=True)
    reload_include: tuple[str, ...] = ()  # Extra extensions to watch (e.g. ".html", ".css")
    reload_dirs: tuple[str, ...] = ()  # Extra directories to watch alongside cwd

    # Security
    secret_key: str = ""

    # Templates
    template_dir: str | Path = "templates"
    autoescape: bool = True
    trim_blocks: bool = True
    lstrip_blocks: bool = True

    # Static files
    static_dir: str | Path | None = "static"
    static_url: str = "/static"

    # SSE
    sse_heartbeat_interval: float = 15.0

    # MCP (Model Context Protocol)
    mcp_path: str = "/mcp"

    # Limits
    max_content_length: int = 16 * 1024 * 1024  # 16 MB
