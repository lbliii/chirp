# htmx 4 beta-5 migration inventory

This audit retains the migration evidence for issue #547. It uses htmx's
upstream `4.0.0-beta5` checker without adding Node, npm, or htmx as a Chirp
runtime dependency.

## Reproduce

From the repository root:

```console
python scripts/htmx4_upgrade_check.py . \
  --output docs/audits/htmx4-beta5-inventory.json
python scripts/htmx4_upgrade_check.py . \
  --check docs/audits/htmx4-beta5-inventory.json
```

The wrapper invokes the pinned upstream command and passes only
repository-owned extensions supported by that checker. It excludes virtual
environments, package directories, caches, Git metadata, and nested `ovrtx`
worktrees. This prevents installed packages and local state from changing the
baseline. The wrapper returns `2` with actionable guidance when optional
tooling is unavailable; Chirp core never imports it.

## Retained beta-5 result

The controlled scan found **175 findings in 36 of 209 files**:

| Upstream category | Count |
| --- | ---: |
| `ext` | 53 |
| `inheritance` | 12 |
| `old-event` | 35 |
| `removed-attr` | 52 |
| `removed-header` | 2 |
| `renamed-attr` | 21 |

The issue's earlier 407-finding estimate is not reproducible against the pinned
beta-5 checker and current repository. It is replaced by the normalized JSON
report, not silently carried forward as a release claim.

## Classification

| Surface | Count | Disposition |
| --- | ---: | --- |
| htmx 2 examples | 144 | Retained. These examples use Chirp's verified htmx 2 tier; changing their markup independently would break that tier. Migrate each example only when it explicitly selects htmx 4. |
| Framework internals | 26 | Retained. Twenty-two are dual-version DevTools listeners or diagnostics; four are the htmx 2 SSE macro dialect. The htmx 4 SSE implementation issues own replacement of the latter. |
| Contract fixtures | 5 | Retained as deliberate htmx 2 boundary fixtures. |

The `app.check()` rule reduces this raw inventory to selected-tier findings:
htmx 2 markup is silent under htmx 2, htmx 4 markup is silent under preview,
and code/pre examples, JavaScript comments, framework-owned templates, and
dynamic attribute bundles are excluded. Compatibility-covered migration debt
is a warning. Cross-tier inert markup, semantic collisions, old SSE/WebSocket
dialects, and events that compatibility mode cannot restore are errors.

The machine-readable finding-by-finding evidence is
[`htmx4-beta5-inventory.json`](htmx4-beta5-inventory.json).
