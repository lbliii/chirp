# Plan: Shell/OOB/SSE Browser Smoke

**Status:** Planned, not executed
**Created:** 2026-05-09
**Scope:** One deterministic browser smoke for app-shell navigation, OOB shell updates, and SSE listener survival.

## Why

Unit and contract tests now cover shell contracts, OOB registry behavior, and
SSE reconnect/replay. They do not prove the live DOM behavior that htmx owns:
listener attachment, inherited `hx-*` attributes, OOB swaps against actual
element IDs, and whether boosted navigation replaces the SSE listener.

The repository currently has no Playwright/browser harness or `tests/browser`
tree, so this remains a scoped plan rather than a claimed browser proof.

## Fixture

Use the smallest shell-style example or fixture that can render:

- a stable outer shell with `hx-boost`;
- a main content target;
- one OOB region in the shell;
- one SSE listener outside the boosted content;
- one boosted link that swaps main content while leaving the SSE listener
  connected.

Do not grow `examples/chirpui/forum_shell` into a product to satisfy this. Add
only the minimal route/template behavior needed for the framework contract.

## Acceptance

The browser smoke must assert all of the following:

- initial page has exactly one SSE listener element with `sse-connect`;
- boosted navigation swaps the main target without inserting a full document
  into the target;
- the SSE listener element still exists after boosted navigation;
- an SSE event updates the expected OOB/swap target;
- no OOB target referenced by the stream is missing from the DOM;
- mobile and desktop viewport screenshots show no overlapping shell controls.

## Command Shape

Prefer a committed test command over a manual checklist:

```text
uv run pytest tests/browser/test_shell_oob_sse_smoke.py -q
```

If the repo adds a different browser-test runner first, update this plan and
the roadmap with the concrete command.

## Not Now

- Broad cross-browser matrix.
- Visual regression baselines.
- Product-specific forum workflows, tenants, moderation, or data schemas.
- Browser proof for request URL scope beyond a tenant-like shell URL once the
  basic smoke is stable.
