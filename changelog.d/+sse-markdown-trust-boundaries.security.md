**SSE and markdown trust boundaries** — `SSEEvent` now rejects event names and IDs containing CR, LF, or NUL characters, rejects negative retry values, and normalizes carriage returns in data frames. `MarkdownRenderer` and `register_markdown_filter()` now sanitize unsafe HTML, event attributes, and unsafe link/image URLs by default.

  **Migration** — Trusted markdown that intentionally preserves raw HTML can pass `sanitize=False`. Apps constructing `SSEEvent(event=...)` or `SSEEvent(id=...)` must pass single-line field values.
