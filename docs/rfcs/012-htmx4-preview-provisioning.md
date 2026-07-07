# RFC 012: Explicit htmx 4 Preview Provisioning

**Status:** Implemented by issue #545

**Issue:** [#545](https://github.com/lbliii/chirp/issues/545)

**Pinned preview:** htmx 4.0.0-beta5 at commit 5300af9e7af8b196f9fbf806cab79a5780b62291.

## Summary

Chirp will reuse the existing AppConfig.htmx and AppConfig.htmx_version fields.
The exact opt-in is AppConfig(htmx=True, htmx_version="4.0.0-beta5"). That
pin selects an immutable internal manifest and injects core, htmx-2-compat,
and hx-sse in that order. Every script receives the live CSP nonce and exact
tier/version metadata. No new config field, helper, CLI flag, environment
variable, or scaffold default is introduced.

The implementation keeps htmx 2 as the default; #543 owns the verified 2.0.10
baseline and #551 owns a future default flip.

## Current surface and goals

Before this implementation, the injection path emitted one explicit jsDelivr core URL, handled
buffered and streaming pages, carried nonces, and deduplicated on the core
data-chirp marker. The htmx_provisioned rule checks presence but not version,
extension set, load order, or markup dialect. Setting the current version to
4 would therefore have created a silent mixed client.

The preview must be exact, reversible, no-build, CSP-safe, and observable by
app.check and DevTools. Beta or RC assets must never become default through a
range. htmx 2 behavior must remain unchanged when preview is disabled.

## Decision

### Reuse the existing version field

htmx=True remains the injection switch. An allowlisted exact htmx 4 value
selects preview; an unknown or malformed htmx 4 value fails before serving.
Historically accepted non-4 pins are not tightened by this issue. Explicit
from_env keyword overrides remain available, but no new CHIRP_HTMX variables
are added.

### Compile one immutable manifest

During freeze, the app compiler resolves a frozen and slotted internal record
containing tier, exact core version, ordered assets and roles, compatibility
features, and rollback baseline. Runtime state, contract snapshots, and
DevTools read that same published record. It is not exported from chirp.

### Pin the beta5 bundle

The ordered assets and SHA-256 browser-spike pins are:

1. dist/htmx.min.js — 192d2d425dda6834bd15973a10f55940cea217a3a840f3f819ffd16063be9a68
2. dist/ext/htmx-2-compat.min.js — 7d7fe881d6ae6d4e661b0113e8504bb15acfc1dc1970f07db109bb20c432e53d
3. dist/ext/hx-sse.min.js — fcc844a52779d8450c1c4796feea8d038943f908b9ee974322c276230e6c86cc

Every URL contains htmx.org@4.0.0-beta5 and an explicit dist path. Classic
defer scripts execute in document order. Compatibility is transitional and
cannot be removed without browser proof for every Chirp integration.

### Mark and deduplicate the bundle

The core retains data-chirp="htmx" and adds data-chirp-htmx-tier="4-preview"
and data-chirp-htmx-version="4.0.0-beta5". Extensions use
data-chirp="htmx-extension" plus exact role/version metadata. Every tag gets
the same nonce. The core marker suppresses the whole injected bundle.

A template that supplies the core marker owns the complete bundle. Preview
checks then require both companion extension roles; a manual core cannot
silently suppress framework assets.

### Keep self-hosting explicit

Self-hosted apps set htmx=False and render the same metadata on local script
URLs. Chirp adds no CDN-base setting. app.check validates roles, versions,
order, duplicates, and markup dialect from templates; DevTools validates the
live DOM and htmx.version. Self-hosted artifact integrity remains deployment
owned.

### Fail loud on incompatible combinations

A new htmx_compatibility category is ERROR for mismatched core/extensions,
missing preview extensions, duplicate roles, unsupported htmx 4 pins, htmx 4
markup on a configured htmx 2 tier, or removed htmx 2 markup that preview
compatibility does not cover. The existing htmx_provisioned severity does not
change. Messages name the template, detected asset or attribute, selected
tier, expected pin, and exact rollback or migration action.

### DevTools and rollback

DevTools reports configured and live versions, extension roles, source URLs,
duplicates, and compatibility state. Request headers alone never prove client
version. Rollback selects the verified htmx 2 pin and removes htmx 4-only
markup; app.check must pass before rollout.

## Security and free-threading

All tags share the request nonce. No inline bootstrap, eval, floating URL, or
new CSP source is added. The manifest publishes once under the freeze lock and
request-local nonce formatting never mutates it.

## Required implementation proof

1. Manifest tests for stable 2, beta5, and rejected htmx 4 pins.
2. Buffered/streaming tests for order, exact URLs, metadata, dedup, and nonce.
3. Contract matrices for missing, duplicate, mismatched, and self-host assets.
4. Production/debug parity for the new ERROR category.
5. Browser proof that core loads once, extensions register in order, old
   compatibility events fire, native SSE initializes, and CSP permits all tags.
6. DevTools configured/live mismatch and rollback tests.
7. Public API, config, site, migration, and towncrier collateral.
8. No scaffold default change before #551.

## Steward signals

Steward: App Lifecycle
Area: Preview manifest publication
Severity: P1
Invariant: Freeze publishes one complete immutable runtime truth.
Evidence: src/chirp/app/compiler.py:157 -> src/chirp/app/AGENTS.md:13
User Impact: Half-published metadata lets checks and runtime disagree.
Required Fix: Publish one frozen internal manifest with runtime and snapshots.
Required Proof: Freeze, runtime-read, and free-threading tests.
Collateral: no public export; lifecycle rationale in this RFC.
Confidence: High
Verification Status:
machine-verified

Steward: Server And Negotiation
Area: Script bundle and live client tier
Severity: P0
Invariant: Core, compatibility, and SSE load once in matched order.
Evidence: src/chirp/server/htmx.py:23 -> tests/test_htmx_inject.py:16
User Impact: Mixed assets silently disable swaps, hooks, or streams.
Required Fix: Resolve an ordered exact-pin bundle and verify it live.
Required Proof: CSP browser load-order, dedup, and registration smoke.
Collateral: DevTools and migration guidance.
Confidence: High
Verification Status:
machine-verified

Steward: Contract Checks
Area: Provisioning and dialect drift
Severity: P0
Invariant: Detectable combinations that make HTML inert fail loud.
Evidence: src/chirp/contracts/rules_htmx_provisioned.py:69
User Impact: A passing startup check can hide a broken htmx 4 page.
Required Fix: Add htmx_compatibility without changing current severity.
Required Proof: Mismatched, missing, duplicate, and manual-template matrix.
Collateral: Contract docs and troubleshooting.
Confidence: High
Verification Status:
machine-verified

Steward: CLI And Scaffolds
Area: Preview opt-in and rollback
Severity: P1
Invariant: Scaffolds retain the verified default until the release gate.
Evidence: src/chirp/cli/templates/v2.py:276
User Impact: A prerelease could become an accidental project default.
Required Fix: Document opt-in and rollback; do not change templates here.
Required Proof: Scaffold output remains unchanged.
Collateral: no scaffold change in this issue.
Confidence: High
Verification Status:
machine-verified

The server and contract stewards converge on mixed delivery as P0.

Steward: Narrative Docs
Area: Compatibility and rollback guidance
Severity: P1
Invariant: Every documented asset and setting traces to an exact source pin.
Evidence: src/chirp/config.py:224 -> docs/public-api.md
User Impact: Loose preview instructions create unreproducible clients.
Required Fix: Document exact bundle, markers, self-hosting, and rollback.
Required Proof: Docs inventory tests and browser-backed hashes.
Collateral: Public API, site migration guidance, and changelog on implementation.
Confidence: High
Verification Status:
machine-verified

## Dependencies, risks, minority report, and not-now

This is the highest-leverage remaining P1 foundation: it unlocks #546 and #547,
the implementations behind #549 and #550, the transport work in #553, and the
safe-default gate in #551. It depends on #543 only for the final rollback pin.

Primary risks are beta asset drift, compatibility/native event duplication,
and manual templates that use the core marker to suppress an incomplete bundle.
The exact allowlist, live browser proof, and fail-loud contract matrix contain
those risks.

Minority report: a dedicated preview helper would be more discoverable than a
version string, but it adds a second public control surface and complicates
rollback. The draft therefore prefers the existing frozen config fields.

Not now: a new config flag, environment variables, configurable CDN base, SRI
policy for arbitrary self-hosted files, scaffold migration, or default flip.

## Decision log and approval gate

Accepted: existing fields, exact allowlist, internal manifest, ordered bundle,
whole-bundle dedup, self-host markers, and fail-loud compatibility checks.
Rejected: a preview boolean, public helper, loose range, configurable CDN base,
implicit extension discovery, and automatic template rewrites.

Implementation changes version validation, injected asset shape, runtime state,
contract defaults, and DevTools. Maintainers approved those exact choices for
issue #545.
