# Structural anti-spaghetti evidence ledger

Decision evidence for [#883](https://github.com/lbliii/chirp/issues/883),
recorded 2026-08-03. This ledger creates no behavior.

## Proven source authorities

| Source | Fact it owns |
| --- | --- |
| `src/chirp/app/hypermedia_program.py` | Frozen routes, templates, blocks, targets, declarations, origin, and stable transitions; `target_block_transitions()` supplies resolved target/block facts. |
| `src/chirp/app/hypermedia_program_compiler.py` | Deduplicates and publishes that program at application freeze. |
| `src/chirp/contracts/rules_fragment_targets.py` | Required/optional target-to-block predicate and repair diagnostic. |
| `src/chirp/contracts/rules_template_declarations.py` | Explicit declaration predicate and origin-bearing diagnostic. |
| `src/chirp/contracts/rules_unreachable_blocks.py` | Bounded Kida-AST composition predicate. |

## Family matrix

| Family | Positive / clean-negative proof | Canaries | Unknown behavior | Decision |
| --- | --- | --- | --- | --- |
| Target/block resolution | `tests/contracts/test_fragment_target_orphans.py`: required positive, optional warning, defined-block clean negative, parse error, override | Mounted app, Lucky Cat, forum-shell | Dynamic runtime target construction | Existing required `ERROR` and optional `WARNING`; unchanged |
| Explicit declaration validity | Declaration-rule coverage validates absent template/block and declaration source; clean app canaries have no declaration error | Mounted app, Lucky Cat, forum-shell | Undeclared dynamic names | Existing `ERROR`; unchanged |
| Composition reachability | `tests/contracts/test_unreachable_blocks.py`: sibling positive; nested, `extends`, empty, and extra-root clean negatives | Mounted app, Lucky Cat, forum-shell | Macros, layouts, intentional dynamic composition | Existing `WARNING`; unchanged |

The three rows above are the only accepted high-precision families. No proposed
inventory addition has zero-false-`ERROR` evidence. Semantic duplicates,
ownership/folder lint, generic duplication, suppression lint, dynamic-name
claims, and scores/gates are rejected because no source-owned fact proves them.

## Reproduction and canary receipt

Passed on 2026-08-03:

```console
.venv/bin/pytest tests/contracts/test_fragment_target_orphans.py \
  tests/contracts/test_unreachable_blocks.py \
  tests/test_mount_app.py \
  examples/chirpui/lucky_cat/test_app.py::TestContracts \
  examples/chirpui/forum_shell/test_app.py::TestForumShell \
  tests/test_release_canary.py -q

.venv/bin/pytest tests/cli/test_scaffold_patterns.py -q
```

The structural/canary command passed with existing Kida migration warnings from
forum templates. The scaffold suite passed. `tests/test_release_canary.py`
verifies the pinned advisory workflow and credential gate only; it does not run
the external downstream application. The downstream canary is **unobserved and
credential-gated** by a maintainer-held token.

## Zero-false-error boundary

An error is permitted only for an absent required target/block or an absent
explicit declaration: each has a compiler-owned required promise, a concrete
absence fact, a repair subject, and intentional clean-negative fixtures. The
other accepted family stays a warning; every rejected family lacks one or more
of those conditions. This evidence therefore does not authorize full #883
closure or any new error behavior.
