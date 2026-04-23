# Changelog fragments

Each fragment is one entry in the next release's changelog. `towncrier build` compiles them into `CHANGELOG.md` and deletes the fragment files.

## Naming

`<+slug>.<type>.md` — the leading `+` keeps them sorted first in listings.

Types match the `[[tool.towncrier.type]]` entries in `pyproject.toml`:

- `added` — new features / APIs
- `changed` — behavior or signature changes (breaking or not)
- `deprecated` — APIs scheduled for removal
- `removed` — removed APIs
- `fixed` — bug fixes
- `security` — CVE / security-sensitive fixes

Examples: `+suspense-defer-blocks.added.md`, `+sse-event-default.changed.md`.

## Format — **no leading `-`**

Fragments are **plain text**. Towncrier prepends the `-` bullet itself.

```markdown
✓ **`Suspense.defer_blocks`** — optional explicit list of blocks to re-render as OOB chunks.

✗ - **`Suspense.defer_blocks`** — optional explicit list of blocks…
```

A leading `- ` produces `- - **…**` in the compiled changelog.

Sub-paragraphs (for multi-part entries) indent with two spaces so towncrier keeps them nested under the bullet:

```markdown
**Breaking — SSE event-name default** — `EventStream` now emits yielded `Fragment`…

  **Migration** — In templates, change `sse-swap="fragment"` to `sse-swap="message"`.
```

## Workflow

- Write the fragment in the same PR as the change.
- Preview: `make changelog-draft` (or `uv run towncrier build --draft`).
- Compile (release time only): `make changelog` (or `uv run towncrier build --yes`).
