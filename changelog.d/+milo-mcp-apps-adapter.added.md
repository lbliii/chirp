**Milo MCP Apps registration boundary** — `chirp.ext.milo.use_milo()` now
verifies explicit canonical command allowlists, matching tool/resource links,
and setup-only template/block bindings at Chirp freeze. It publishes immutable
inspection records without mutating the caller-owned Milo CLI.
