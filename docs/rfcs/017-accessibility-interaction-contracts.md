# RFC 017: Accessibility Contracts For Dynamic Interaction Paths

**Status:** Evidence phase complete — family decisions recorded; no new checks, CLI flags, or defaults ship
**Issue:** [#346](https://github.com/lbliii/chirp/issues/346)
**Parent:** [#335](https://github.com/lbliii/chirp/issues/335)
**Related:** RFC 008, RFC 013, RFC 015, #347
**Created:** 2026-07-08

## 1. Context

Chirp currently reports five accessibility categories while scanning template
source:

- `a11y_interactive` — htmx URL attributes on a non-interactive element with
  neither `role` nor `tabindex`;
- `a11y_label` — form controls without a literal label association or ARIA
  label;
- `a11y_alt` — `<img>` elements without `alt`;
- `a11y_heading` — heading levels that skip within one template source; and
- `a11y_landmark` — layout sources without a literal `<main>` or
  `role="main"`.

All five are `WARNING` by default and can be promoted individually with the
existing `app.override_contract_severity(...)` setup API. They protect useful
static facts, but they do not model what happens after htmx, OOB, SSE, dialog,
popover, or View Transition updates.

Issue #346 asks for contracts around focus handoff, dynamic announcements, and
dialog escape paths. Those properties depend on relationships between a
trigger, route, render block, DOM target, and post-swap state. They should
consume Chirp's compiled hypermedia graph rather than become more independent
regular expressions.

This RFC defines the research direction and a proposed severity posture. It
does not add `chirp check --a11y strict`, change any existing severity, add a
template attribute, inject browser code, or claim WCAG compliance.

## 2. Evidence snapshot

### 2.1 Current implementation

| Surface | Current behavior | Evidence |
| --- | --- | --- |
| Five template checks | Source-regex checks, all `WARNING` | `src/chirp/contracts/rules_accessibility.py` |
| Severity overrides | Each category can be promoted independently | `tests/contracts/test_hypermedia.py` |
| Rule coverage | Focused positive/negative fixtures for all five categories | `tests/contracts/test_accessibility.py` |
| Dialog target wiring | Literal `commandfor` IDs and command values are validated | `src/chirp/contracts/rules_commands.py` |
| View Transition safety | Broad live-update containers receive `view_transition_scope` warnings | `src/chirp/contracts/rules_swap.py` |
| Compiled relationships | Routes, templates, blocks, targets, and transitions share stable identities | `src/chirp/app/hypermedia_program.py`, RFC 008 |
| Kida analysis | Kida also has AST-level image, label, heading, and html-lang analysis, but Chirp does not currently consume it as these five categories | [Kida v0.11.0 a11y analysis](https://github.com/lbliii/kida/blob/v0.11.0/src/kida/analysis/a11y.py) |

The current checks do not validate:

- which element retains or receives focus after a swap;
- whether an unattended SSE/OOB update is announced appropriately;
- whether a dialog has an accessible name, initial focus policy, visible close
  path, and focus return; or
- focus state after a View Transition completes.

### 2.2 Canary audit

On Chirp `main` at `9ada3ba4` with `chirp-ui` 0.11.0, these commands produced
zero `a11y_*` findings:

```bash
PYTHONPATH=. .venv/bin/chirp check \
  examples.chirpui.forum_shell.app:app --json --include-info

PYTHONPATH=. .venv/bin/chirp check \
  examples.chirpui.lucky_cat.app:app --json --include-info
```

The forum check scanned 254 templates; Lucky Cat scanned 273. This is evidence
that the existing five rules have no current canary noise. It is not evidence
that the applications have no accessibility defects.

A grep inventory over the application-owned page trees found:

- 133 htmx request/target/swap or focus-scroll markers;
- 58 SSE/OOB/live-region/status markers; and
- 19 dialog/popover/command/focus markers.

These are candidate interaction surfaces, not violations. New rules must be
measured against them before any default severity is accepted.

## 3. Decision summary

Accessibility checks should evolve in two layers:

1. **Literal document checks** continue to validate local HTML facts.
2. **Interaction-path contracts** query compiled trigger → route → block →
   target relationships and validate explicitly declared focus/announcement
   behavior.

The first interaction increment should add three independently reviewable
families:

- `a11y_focus` for htmx/OOB swap focus preservation or handoff;
- `a11y_live_region` for unattended SSE/OOB announcements; and
- `a11y_dialog` for native dialog/popover naming, close paths, and focus proof.

Each family requires its own fixture and canary receipt. They must not be
bundled into one “strict accessibility” switch whose failures are hard to
attribute.

## 4. Existing-category severity posture

An explicit strict posture may promote only findings whose current literal
analysis is reliable enough to block a deploy. The proposed starting matrix is:

| Category | Default | Proposed explicit strict posture | Rationale |
| --- | --- | --- | --- |
| `a11y_alt` | `WARNING` | `ERROR` | A literal `<img>` without any `alt` is a concrete missing accessible-text decision. |
| `a11y_label` | `WARNING` | `ERROR` | A literal labelable control with no detected label/ARIA association is actionable; dynamic associations still require browser proof. |
| `a11y_interactive` | `WARNING` | `ERROR` | A non-interactive htmx trigger with neither role nor keyboard position has no static keyboard path. The rule still does not prove key activation when only one attribute is present. |
| `a11y_heading` | `WARNING` | `WARNING` | Per-file heading order can disagree with the composed page outline; promotion needs composition-aware analysis. |
| `a11y_landmark` | `WARNING` | `WARNING` | A layout may receive its main landmark through composition/macros; promotion needs compiled layout proof. |

This table is a proposal for maintainer review, not a behavior change. The
existing default remains `WARNING` for every category.

The first implementation should document existing per-category overrides
instead of adding `chirp check --a11y strict` or an `AppConfig` field. A CLI
profile is public command behavior and should be considered only after the
category set, false-positive budget, and deploy semantics stabilize.

## 5. Focus contracts

### 5.1 Browser baseline

htmx preserves focus for inputs with stable IDs across swaps. Its
`focus-scroll:true` modifier controls whether the focused element is scrolled
into view; it does not declare a new focus destination. See the official
[`hx-swap` focus-scroll documentation](https://htmx.org/attributes/hx-swap/).

Chirp should distinguish two policies:

- **preserve** — the active element remains present with the same stable ID;
- **move** — focus intentionally moves to a declared element after settlement.

No policy should mean “guess the first focusable descendant.”

### 5.2 Proposed declaration

Focus is DOM behavior, so the proposed declaration is a literal HTML data
attribute on the element that owns the request or swap boundary:

```html
<form
  hx-post="/tasks"
  hx-target="#task-list"
  data-chirp-focus="preserve">
  ...
</form>

<button
  hx-delete="/tasks/42"
  hx-target="#task-list"
  data-chirp-focus="#task-list-heading">
  Delete
</button>
```

This is proposed public template syntax, not shipped behavior.

For `preserve`, static validation requires a literal ID on the focus-bearing
control and evidence that the response block preserves that ID. For a selector,
the compiler resolves a literal ID in the target render surface. Dynamic
selectors need a validated declaration or remain unproven.

A move policy also needs a small, CSP-compatible htmx settlement helper or an
accepted upstream primitive. The contract must not recommend inline
`hx-on::after-settle` JavaScript as its only implementation. Runtime focus
movement therefore requires a separate implementation review.

### 5.3 Compiled relationship

The private graph may attach a frozen focus policy to an existing target or
transition identity:

```python
@dataclass(frozen=True, slots=True)
class FocusContract:
    transition_id: str
    policy: Literal["preserve", "move"]
    selector: str | None
    origin: SourceOrigin
```

The exact internal shape is not public API. It must be deterministic, compiled
under the freeze lock, and consumed by checks, DevTools, and browser coverage
without rescanning a parallel model.

### 5.4 Proposed diagnostics

| Condition | Proposed severity |
| --- | --- |
| Declared focus selector does not exist in the response block | `ERROR` |
| `preserve` control has no stable literal ID | `ERROR` |
| Outer swap removes the declared preserve target | `ERROR` |
| Destructive list mutation has no declaration | `WARNING` after canary audit |
| Dynamic selector cannot be proven | `WARNING` or require explicit registry proof |

Only invalid explicit declarations should start as `ERROR`. Missing declarations
must remain warning-only until real-app false-positive evidence supports a
stronger default.

## 6. Live-region contracts

Live-region policy should use standard ARIA, not a Chirp-specific replacement.
The relevant target contains `aria-live="polite"` or `"assertive"`, or a role
whose live-region semantics are deliberate (`status`, `log`, or `alert`). See
the WAI-ARIA [`aria-live` definition](https://www.w3.org/TR/wai-aria-1.2/#aria-live).

The initial rule should examine unattended updates:

- `sse-swap` targets;
- registered OOB regions updated outside a focused request;
- signal-render targets that update asynchronously; and
- validation/error blocks intended to announce status.

Ordinary user-initiated htmx navigation must not automatically require a live
region. Announcing every swap creates noise rather than accessibility.

Proposed validations:

| Condition | Proposed severity |
| --- | --- |
| Explicit live-region target references no compiled block/DOM ID | `ERROR` |
| `role="alert"` is used for high-frequency ticker data | `WARNING` |
| Unattended SSE target has no live-region policy | `WARNING` initially |
| OOB producer and target disagree on region identity | Existing OOB severity plus accessibility context |
| Region replaces its own ARIA attributes during an inner/outer swap | `ERROR` when statically proven |

`aria-atomic` and `aria-relevant` remain author choices. Chirp may provide
contextual guidance, but it should not fabricate one universal policy for
tables, logs, validation errors, tickers, and toasts.

## 7. Dialog and popover contracts

Native `<dialog>` is the preferred modal primitive. Browser-managed modal
dialogs move focus on open, constrain the tab sequence, and normally return
focus to the invoker. W3C's [HTML dialog technique](https://www.w3.org/WAI/WCAG22/Techniques/html/H102.html)
and [modal dialog pattern](https://www.w3.org/WAI/ARIA/apg/patterns/dialog-modal/)
also require an accessible name and recommend a visible close control.

Chirp already validates literal `commandfor` targets and command values. The
proposed `a11y_dialog` family should build on that relationship and check:

- a literal accessible name via `aria-label`, `aria-labelledby`, or an
  accepted native naming relationship;
- at least one visible close/cancel control;
- an initial focus candidate (`autofocus`, explicit focus contract, or a
  browser-proven native default);
- a literal invoker relationship for focus return when statically knowable;
- `closedby`/command policy that does not remove every keyboard escape path;
  and
- custom `role="dialog"` surfaces only when their focus containment behavior is
  explicitly proven.

Native-dialog use is not itself an error if one of these facts is dynamic. The
rule should report what remains unproven and require browser evidence rather
than claiming a static guarantee.

Popover checks should distinguish automatic popovers, which have light-dismiss
behavior, from manual popovers that need an explicit close path. A generic
“every popover must trap focus” rule would be wrong; popovers are not all modal.

## 8. View Transitions

View Transition identity and focus are orthogonal. An element can animate
smoothly while keyboard focus is lost or left on a removed node.

The existing `view_transition_scope` check remains responsible for broad
animation scopes around OOB/SSE regions. `a11y_focus` should query the same
compiled transition and assert focus after htmx settlement and, where used,
after the View Transition promise completes.

No focus contract should require animation, and reduced-motion behavior must
not change focus results.

## 9. Browser and property proof

Static analysis must be paired with browser assertions over
`document.activeElement` and the accessibility-facing DOM:

| Scenario | Required proof |
| --- | --- |
| Input validation fragment | Focus remains on the invalid control with its stable ID; error relationship is present. |
| Successful create | Focus moves to a declared heading/status or remains on a stable form control by policy. |
| Deleted list row | Focus moves to the next logical item or list heading, never `<body>` by accident. |
| SSE/OOB update | Live region remains present and receives the update without stealing focus. |
| Dialog open/close | Focus enters the dialog, Escape/close works, and focus returns to the invoker or declared successor. |
| View Transition | Final focus equals the non-animated path. |

Property-style fixtures should generate or enumerate swap shapes rather than
pretend every business workflow can be fuzzed. Useful invariants include:

- every resolved focus selector exists exactly once in the resulting DOM;
- no successful swap leaves `activeElement` inside a detached subtree;
- an unattended live update does not change `activeElement`; and
- closing a dialog never returns focus to an inert/removed element.

Playwright remains the browser authority. `app.check()` catches detectable
wiring mistakes; it does not replace axe-core, assistive-technology testing, or
human review.

## 10. False-positive gate

Before any new category becomes deploy-blocking:

1. run it over Lucky Cat and forum_shell;
2. classify every finding as defect, accepted declaration gap,
   dynamic/unproven, or false positive;
3. add focused fixtures for accepted defects and every false-positive shape;
4. keep the raw receipt with the implementation PR; and
5. require zero false `ERROR`s on both canaries.

The current zero-finding baseline for the original five categories is the
starting receipt, not permission to promote new rules without measurement.

## 11. Delivery sequence

1. **RFC review:** accept or revise syntax, category boundaries, and proposed
   strict posture. No behavior change.
2. **Literal-rule hardening:** reconcile Chirp's regex checks with Kida's AST
   analysis and composed-template identities before promotion.
3. **Focus graph increment:** compile explicit focus declarations and add
   declared-only diagnostics.
4. **Live-region increment:** connect SSE/OOB/signal producers to standard ARIA
   policy on their targets.
5. **Dialog increment:** extend existing command target wiring with accessible
   name, close, and browser focus proof.
6. **Canary/browser receipt:** prove the matrix above on fixtures, Lucky Cat,
   and forum_shell.
7. **Public strict profile:** only then consider a CLI convenience, docs,
   changelog, and compatibility policy.

Every implementation step needs the repository's explicit check-in before
changing a severity/default, CLI shape, template contract, compiler record, or
runtime focus helper.

### 11.1 Issue #686 evidence receipt

The evidence fixture and browser assertions now live at
`tests/contracts/templates/a11y_interactions.html` and
`tests/contracts/test_accessibility_interactions_browser.py`. The raw,
machine-checked canary counts and false-result boundaries live in
`tests/contracts/a11y_interaction_evidence.json`.

| Family | Decision | Evidence boundary |
| --- | --- | --- |
| focus continuity | revise | Stable-ID handoff is browser-provable, but requiring declarations on every request-bearing element would be noisy. Start with invalid explicit declarations only. |
| live regions | accept | Standard ARIA policy survives inner updates and can be lost by outer replacement. Limit the future graph rule to proven unattended producers. |
| dialog and popover | revise | Native modal behavior and automatic popover dismissal are sound controls; custom modals and manual popovers need separate policies. |
| reduced motion | no-go | Motion preference changes computed animation without changing the focus result. Keep browser equivalence proof; do not create a standalone contract category. |

After stripping Kida comments, the Lucky Cat canary contains 22 request-bearing
tags, 11 live-update markers, 11 live-policy markers, one native dialog, and one
reduced-motion marker. Forum Shell contains one request-bearing tag and none of
the other candidate families. Existing `a11y_*` findings remain zero on both.
These receipts reject blanket missing-policy diagnostics and retain a path for
narrow declared-only or proven-producer checks in separately reviewed children.

## 12. Success criteria mapping

| #346 criterion | RFC disposition |
| --- | --- |
| Declarative focus syntax vs sidecar | Prefer literal `data-chirp-focus` on the owning DOM boundary; compile it into the shared graph. Runtime move behavior remains separately reviewed. |
| Which five checks become `ERROR` in strict mode | Propose alt, label, and interactive; keep heading and landmark warning-only until composition-aware. |
| View Transitions integration | Reuse the compiled transition; animation never substitutes for focus proof. |
| False-positive audit | Current five yield zero findings on 254 forum and 273 Lucky Cat templates; every new category needs its own raw canary receipt. |
| Strict fixture catches focus drop | Future implementation/browser deliverable, not claimed by this RFC. |
| Zero false `ERROR`s | Mandatory gate before severity promotion. |

## 13. Non-goals

- Claiming WCAG conformance from static checks.
- Shipping axe-core or an assistive-technology emulator in core.
- Guessing focus destinations from visual layout or CSS order.
- Requiring live regions for every htmx swap.
- Treating every popover as a modal dialog.
- Adding a global `AppConfig` strictness flag before category behavior settles.
- Changing existing accessibility severities in this RFC.

## 14. Status and collateral

This document changes no public API, CLI, `AppConfig`, template behavior,
contract category, severity, runtime helper, dependency, example, or generated
site output.

No changelog: the evidence phase adds fixtures and a decision receipt only;
user-visible behavior has not changed.
