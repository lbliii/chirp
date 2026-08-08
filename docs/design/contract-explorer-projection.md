# Contract Explorer private projection

This note documents the internal Phase 1 read model from RFC 021. It is an
implementation detail, not a public Python API, serialized schema, CLI format,
debug endpoint, or compatibility promise.

## Authority and lifecycle

`src/chirp/contracts/explorer_projection.py` accepts exactly two authorities:

- the frozen `HypermediaProgram` published by the existing app compiler; and
- an already-finalized `CheckResult`, or `None` when findings and coverage are
  unavailable.

The builder does not accept an `App`. It cannot inspect mutable registries,
parse or render templates, execute routes, or compile relationships. Every
output collection is a deterministically sorted tuple of frozen, slotted
records, so the returned projection is published as one complete immutable
value.

## Internal record shape

The projection contains:

- route, template, block, and target nodes copied from compiler identities;
- transition edges copied without changing their resolved state or provenance;
- finalized findings with severity, category, message, location, and details;
- coverage counters copied into sorted key/value tuples; and
- explicit analysis gaps for relationship families the compiler does not model.

Node attributes are closed by node kind:

| Kind | Attributes |
| --- | --- |
| route | method, name, path |
| template | extends, is_page, is_page_leaf, name |
| block | name, template_id |
| target | contract_name, fragment_block, required, target_id |

Compiler load-error strings are intentionally not copied. Origins remain
bounded to logical template names, registry identifiers, and module-qualified
handler names already supplied by the compiler; no absolute path or source text
is introduced by the projection.

## Finding correlation

Correlation uses only exact structured `route` and `template` locations from a
finding. It never searches finding messages.

- `bound` means every supplied location matched exactly one compiled node.
- `ambiguous` means an exact route path matched several method-specific nodes.
- `unbound` means no structured location was supplied or at least one supplied
  location had no compiled match.

The projection retains every candidate identity for an ambiguous location so a
consumer cannot silently choose a route method.

## Honest gaps

The current compiler publishes route-to-template, route-to-block,
template-to-block, and target-to-block edges. It does not yet publish complete
OOB, Suspense, SSE, form, auth, signal, accessibility, or return-intent-kind
topology. Those families remain named analysis gaps even when their existing
contract findings are present. Adding their topology belongs in the existing
compiler; the projection must not grow a parallel scanner.

When `CheckResult` is unavailable, findings and coverage are empty and the
projection includes `contract_findings_and_coverage:unavailable`. Consumers
must render that state as unavailable, never clean.

## Related: architecture gap diagnostics

Approved dead / orphan / unreachable / suppressed / unproven / unobserved
inventory for agents lives in the sibling private module
`src/chirp/contracts/gap_diagnostics.py`. See
[`architecture-gap-diagnostics.md`](architecture-gap-diagnostics.md). That
projection copies existing check findings and override inventory; it does not
replace this topology projection or promote non-blocking categories to ERROR.
