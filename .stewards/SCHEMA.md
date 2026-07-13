# Steward Manifest Schema

`.stewards/manifest.toml` is the source of truth for generated `AGENTS.md`
maps. Stable repository knowledge belongs in the manifest; generated maps stay
small enough for ordinary task context.

Top-level fields define the network, active-context budget, code-domain
coverage roots, project pillars, progressive search policy, and stop-and-ask
boundaries. `operating_rules` preserves repository-wide maintainer workflows;
`done_criteria` renders exact proof expected before handoff.

Each `[check.<id>]` registers an exact command and an existing proof location.
Optional `proof_contains` text prevents a check from being wired to an unrelated
file merely because the path exists.

Each `[[steward]]` owns one generated map and may declare code, test, and docs
paths, guardrails, and typed graph edges to other stewards.

Each `[[invariant]]` is `machine`, `manual`, or explicit `none`:

- `machine` names a registered check through `enforced_by`.
- `manual` names an evidence file and stable text anchor.
- `none` records visible verification debt rather than overstating coverage.

`[judgment.<steward>]` contains non-enforceable advocacy, refusal patterns, and
the peers a steward serves.

Generated maps render exact machine-check commands. Ordinary agents should not
open this manifest or the protocol merely to translate check identifiers.

Validate with:

```bash
python .stewards/project.py --check
python .stewards/verify.py --coverage
```
