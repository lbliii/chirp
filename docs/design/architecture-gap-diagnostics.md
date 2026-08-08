# Architecture gap diagnostics (private projection)

This note documents the internal architecture-gap projection approved by
RFC 028 / issue [#885](https://github.com/lbliii/chirp/issues/885). It is an
implementation detail, not a public Python API, CLI format, serialized schema,
or compatibility promise.

## Authority

`src/chirp/contracts/gap_diagnostics.py` accepts:

- an optional frozen `HypermediaProgram` (topology authority);
- an optional finalized `CheckResult` (existing `dead` / `orphan` /
  `unreachable_block` findings);
- an optional severity-override map from `App.override_contract_severity`; and
- an optional frozenset of observed transition IDs from a runtime evidence
  overlay.

The builder does not accept an `App`, does not parse templates, does not execute
routes, and does not add a second topology scanner. It never promotes findings
to `ERROR`.

## Gap kinds

| Kind | Source | Meaning |
| --- | --- | --- |
| `dead` | Existing `dead` findings | Unreferenced template (architecture debt) |
| `orphan` | Existing `orphan` findings | Unreferenced route; static navigation is unproven |
| `unreachable_block` | Existing `unreachable_block` findings | Sibling page block outside known composition |
| `suppressed` | Severity override inventory | Policy intervention; never clean coverage |
| `unproven` | Unresolved enhancement fallback edges | Concrete dynamic edge without a resolved destination |
| `unobserved` | Missing checks or unmatched evidence | Behavioral evidence unavailable or not observed |

Standing caveats that apply to every app remain in `notes`:

- `static_reachability_is_not_behavioral_coverage`
- `severity_overrides_are_suppressed_never_clean`
- `undeclared_dynamic_edges_remain_unproven`

Undeclared runtime template selection that never entered the compiler stays in
those notes rather than fabricating edges. `app.declare_template(...)` remains
the explicit static promise for dynamic registries.

## Clean vs complete

- `is_clean` is False when any debt finding, severity override, or unproven
  enhancement edge is present. Suppressions never count as clean.
- `is_complete` additionally requires available checks, present behavioral
  evidence, and zero unobserved gaps.
- Missing `CheckResult` or evidence is projected as `unobserved`, never as a
  silent pass.

## Consumers

Contract Explorer and agent tooling may compose this report with the private
explorer topology projection and evidence overlay. This module does not change
`app.check()` severities, CLI exit codes, or deploy gates.
