# RFC 025: App-owned UI, template roles, and theme ownership

**Status:** Accepted — architecture decision only; no scaffold or runtime behavior changes ship in this RFC
**Issue:** [#862](https://github.com/lbliii/chirp/issues/862)
**Parent:** [#856](https://github.com/lbliii/chirp/issues/856)
**Implementation children:** [#858](https://github.com/lbliii/chirp/issues/858), [#859](https://github.com/lbliii/chirp/issues/859), [#860](https://github.com/lbliii/chirp/issues/860), [#863](https://github.com/lbliii/chirp/issues/863)
**Created:** 2026-07-17

## 1. Context

Chirp needs a useful default UI story without owning a design system. The
current default is not deterministic:

- `chirp new` selects ChirpUI or non-ChirpUI files according to whether
  `chirp_ui` happens to be importable;
- template setup automatically adds the ChirpUI package loader and registers
  ChirpUI filters and globals when that package is importable; and
- generated theme hooks are coupled to package-owned assets and runtime
  assumptions.

As a result, identical application configuration can produce different files
and template environments on two developer machines. It also blurs ownership:
applications cannot tell whether their visual language belongs to their source
tree, Chirp, Kida, or ChirpUI.

This RFC freezes the smallest boundary needed by the implementation children.
It does not introduce an API, change `AppConfig`, alter rendering, or retire
ChirpUI.

## 2. Decision

1. A new Chirp application's UI is **Kida components plus app-owned templates,
   CSS, theme values, and visual identity**.
2. Chirp owns page discovery, named-block rendering, hypermedia transport,
   CSP plumbing, and UI-neutral focus/history/OOB/shell handoff contracts. It
   does not own component appearance or a token runtime.
3. Route pages remain the one full-page, htmx fragment, OOB, Suspense,
   streaming, and SSE render surface. A separate HTMX partial tree is not
   allowed.
4. Local component and shared-template roots are explicit. Merely installing a
   package must not change generated files, loaders, filters, globals, assets,
   or browser behavior.
5. `use_chirp_ui(app)` and explicit ChirpUI scaffold selection remain the
   compatibility path until a separate retirement decision. ChirpUI is never
   imported by core default behavior.
6. Theme preference is server-validated and persisted in a cookie. The server
   renders `data-theme` as `system`, `light`, or `dark` on the root element.
   Local storage is not a second source of truth.
7. The baseline theme requires no inline pre-paint script. Server-rendered root
   state and CSS media queries establish the first paint; app-owned JavaScript
   progressively enhances the control.
8. `chirp check` validates framework contracts. Directory taxonomy, extraction
   judgment, token completeness, and visual style are guidance rather than
   framework errors.

## 3. Template roles

The roles are semantic, not five interchangeable ways to split HTML.

### 3.1 Layouts

Layouts own the document or persistent shell, landmarks, shared asset links,
and the outlet where route content is composed.

- `pages/**/_layout.html` is Chirp's discovered, inherited route-layout
  contract.
- `templates/layouts/` is an optional scaffold convention for app-owned shared
  layout implementations. Chirp does not discover that directory by name; an
  application makes the root explicit and composes those templates from its
  route layouts.
- A layout must not become a second page template or define sibling page
  response blocks that hide route ownership.

### 3.2 Route pages

A route page is the route-owned `page.py` plus `page.html` pair. `page.html`
defines the named blocks used by every negotiated representation of that
route.

Full navigation, plain-form failure, htmx navigation, local fragments, OOB
updates, Suspense chunks, streaming HTML, and SSE payloads select from that
same logical template contract. Shared components and patterns may render
inside those blocks; they do not replace the block contract.

### 3.3 Reusable Kida components

Components are reusable Kida definitions with explicit props and slots. They
own a coherent semantic element or interaction boundary and may encapsulate an
accessibility invariant. They do not own route loading, response negotiation,
or application-wide mutable state.

The framework-neutral component model, call validation, and authoring grammar
belong to Kida. Chirp owns only explicit loader wiring, scaffold examples, and
the way components participate in Chirp's existing render surface.

### 3.4 Product patterns

Patterns compose components and markup around product vocabulary such as a
search result, settings panel, or activity feed. They are deliberately
application-specific. A pattern may be reused across routes without being
promoted to a universal primitive.

Patterns do not create independent HTTP or fragment endpoints. The route page
that uses a pattern still owns all named response blocks.

### 3.5 Private partials

Private partials are rare, context-bound template implementation details. They
are appropriate when extracting a long local branch improves readability but
an explicit reusable component API would add ceremony without reuse or an
independent invariant.

Private partials:

- live under an app-owned `_partials/` convention;
- may depend on the caller's context;
- are not registered as response targets; and
- must not mirror route pages into a parallel `partials/` response tree.

## 4. Extraction heuristics

Markup remains inline in its route page when it is short, used once, and clear
in route context. Extract it only when the extraction creates a meaningful
boundary:

| Evidence | Destination |
| --- | --- |
| Reused semantic unit, explicit prop/slot API, independently testable behavior, or accessibility invariant | Kida component |
| Product-specific composition reused across pages or large enough to obscure route intent | Product pattern |
| One-use, context-bound branch whose length obscures the owning template | Private partial |
| No reuse, no independent invariant, and no readability gain | Keep inline |

A pass-through wrapper that only renames existing markup is not a component.
Neither a line-count threshold nor anticipated future reuse is sufficient on
its own.

## 5. Directory and filename boundary

The generated application should demonstrate this shape:

```text
pages/
  _layout.html
  page.py
  page.html
templates/
  layouts/
  components/
    primitives/
    controls/
    feedback/
    chrome/
  patterns/
  _partials/
static/
  css/
    tokens.css
    base.css
    components.css
    patterns.css
    pages.css
  js/
    theme.js
    interactions.js
```

Only the existing page-discovery names under `pages/` are framework contract.
The `templates/` groups and CSS/JavaScript filenames are generated,
app-editable conventions. Chirp must not reserve them, scan them by name, or
require an application to retain the scaffold taxonomy.

The scaffold should configure its roots explicitly, using existing template
configuration and integration seams. A package loader is likewise activated by
an explicit integration, never by an importability probe.

## 6. Styling and visual ownership

Generated tokens and styles are ordinary application source from the moment
they are created.

- `tokens.css` defines app-chosen semantic custom properties for color,
  typography, spacing, radius, shadow, motion, focus, and layout.
- Component, pattern, and page layers consume those semantic properties.
- The application owns values, naming beyond the generated starter set,
  component classes, asset choices, and visual identity.
- Chirp does not ship a token manifest, registry, compiler, CSS-in-Python
  model, component theme package, or mandatory frontend build.
- Styling alone must not enable Alpine, add a browser runtime, broaden CSP, or
  activate an optional dependency.

The CSS files are a useful ordering convention, not a public cascade API.
Applications may combine, rename, preprocess, or replace them.

## 7. Theme contract

### 7.1 Root attributes

The generated shell uses:

```html
<html data-theme="system">
```

`data-theme` records the user's preference and accepts exactly `system`,
`light`, or `dark`. CSS maps `system` through
`prefers-color-scheme`; an explicit value overrides that media preference.
Because the attribute records preference rather than a computed color, system
changes can take effect through CSS without rewriting the DOM.

`data-skin` and `data-density` are optional app extension points. Chirp assigns
them no values or semantics. If an application uses them, it defines and
validates a closed value set before rendering either attribute.

### 7.2 Persistence and no-JavaScript behavior

The server validates the submitted theme value against the three-value set,
stores it in an app-owned cookie, and renders the validated value on every full
document response. The generated starter may call that cookie `theme`, but the
name is scaffold source rather than a Chirp protocol.

The cookie is the persistence source of truth. Local storage stores no theme
preference, so navigation cannot encounter competing values. Applications set
normal cookie protections for their deployment (`Path=/`, `SameSite=Lax`, and
`Secure` on HTTPS); the value is not authorization or trusted identity.

The theme control is a normal server form. Without JavaScript it submits the
new value, receives the cookie, and redirects to a full document carrying the
new root attribute. App-owned `static/js/theme.js` may update the root
attribute immediately and submit the same server action in the background, but
the server path remains authoritative.

### 7.3 First paint and CSP

The standard server-rendered posture needs **zero inline pre-paint script**:

- the server already knows the cookie before rendering `<html>`;
- explicit light or dark is present before CSS is evaluated; and
- system mode is resolved by CSS during the same style calculation.

The enhanced control script is a same-origin external asset and does not need
an inline-script exception. If an application chooses a different cached or
static-shell architecture that genuinely requires an inline bootstrap, it must
use Chirp's live request nonce support; that is an application-specific design,
not part of the default scaffold contract.

### 7.4 Tenant and user overrides

Untrusted values must never be interpolated into a `<style>` element, style
attribute, class name, or custom-property declaration.

The preferred override is an allowlisted identifier rendered as `data-skin`
or a link to a same-origin CSS asset whose contents were validated or compiled
at write time. Runtime-generated token assets must use an allowlist of property
names and value grammars, a CSS content type, and a stable cache identity.
Arbitrary user dictionaries and arbitrary CSS text are outside this contract.

## 8. Chirp infrastructure boundary

Chirp continues to own behavior that must remain consistent regardless of an
application's visual system:

- named-block selection and fail-loud missing-block behavior;
- full/plain/htmx/OOB/Suspense/streaming/SSE negotiation and transport;
- CSP header and nonce plumbing;
- UI-neutral focus settlement, title/history updates, and announcement
  handoff where those contracts are implemented;
- OOB transport and shell-action semantics; and
- deterministic template, component-root, and integration registration at
  application freeze.

Applications own the HTML used to present those semantics, the focus targets
they declare, component markup, CSS classes, tokens, theme values, icons, and
visual affordances. A generic Chirp helper may emit safe semantic HTML, but it
must not require ChirpUI classes or prescribe a theme.

## 9. `chirp check` boundary

`chirp check` validates facts that affect framework correctness and can be
proved from the frozen application:

- named blocks, targets, and render relationships resolve;
- required visible blocks fail loud rather than producing empty HTML;
- template and component roots are explicitly registered;
- an explicit optional integration supplies the templates, filters, globals,
  and assets its application references; and
- CSP, focus, history, OOB, and shell handoff declarations are internally
  consistent when Chirp has a typed contract for them.

It does not enforce the scaffold's folder taxonomy, CSS filenames, token
coverage, extraction taste, visual style, or use of `data-skin` and
`data-density`. Those are documentation and scaffold guidance. A diagnostic
for legacy ambient ChirpUI assumptions should name the missing explicit
integration and migration action; the mere presence or absence of an installed
package is not itself a finding.

No contract severity, `AppConfig` field, CLI flag, or public template syntax is
accepted by this RFC. Each implementation child must bring any such public
surface and its false-positive evidence back for the required approval.

## 10. ChirpUI compatibility boundary

During migration:

- `use_chirp_ui(app)` is the explicit compatibility integration for existing
  applications;
- `chirp new --with-chirpui` may remain an explicit compatibility scaffold;
- an installed but unconfigured `chirp_ui` package has no effect;
- Chirp core does not import ChirpUI, copy its components into core, or expose
  its filters and globals by ambient fallback;
- ChirpUI remains an optional dependency and its absence cannot break the
  app-owned default scaffold; and
- removing the explicit integration or designing existing-application
  migrations belongs to a later retirement epic.

An application that references ChirpUI templates or helpers must opt in to the
integration. An application that does not opt in gets the same generated files
and template environment whether ChirpUI is installed or absent.

## 11. Affected-area review

| Area | Decision impact |
| --- | --- |
| Templating | Preserve one logical route template and named blocks; use explicit roots; add no partial-response architecture. |
| CLI | Generate deterministic app-owned files; installed packages are inert; directory layers remain editable conventions. |
| Security | Prefer server-rendered validated attributes and same-origin assets; keep inline script and arbitrary CSS out of the baseline; preserve CSP nonce infrastructure for explicit uses. |
| Accessibility | Theme controls retain a plain form path; system preference works in CSS; focus, announcements, forced colors, and reduced motion remain semantic behavior rather than visual-token guesses. |
| Kida | Kida owns typed component definitions, props/slots, discovery primitives, and call validation; Chirp does not add framework-specific semantics to Kida's loader. |
| Contracts | Validate broken explicit relationships, not UI taste; any new severity or public declaration requires its own evidence and approval. |
| Public API | This decision adds no `AppConfig` field, top-level import, return type, or CLI default by itself. Implementation children must move public collateral together. |

## 12. Rejected alternatives

| Alternative | Reason rejected |
| --- | --- |
| Move ChirpUI components or tokens into Chirp core | Makes a visual system mandatory and expands core ownership beyond hypermedia infrastructure. |
| Auto-detect ChirpUI or another component package | Makes application behavior depend on the developer environment and weakens optional-dependency isolation. |
| Create dedicated HTMX partial templates | Splits full and fragment truth and violates the named-block architecture. |
| Add a Chirp token registry or CSS generator | Creates a second styling runtime and makes generated values framework-owned. |
| Persist theme in both cookie and local storage | Creates two authorities with synchronization and first-paint failure modes. |
| Require an inline pre-paint bootstrap | Is unnecessary for server-rendered root state and increases CSP complexity. |
| Render arbitrary tenant token dictionaries inline | Turns untrusted data into executable CSS and weakens cache and CSP boundaries. |
| Require Alpine or a frontend build tool | Breaks the ordinary-CSS, progressive-enhancement, optional-extra baseline. |

## 13. Delivery and proof

This RFC is the decision collateral for #862. It intentionally changes no
runtime behavior, so behavioral acceptance is deferred to the implementation
children:

1. #858 owns generated tokens, theme form/script behavior, CSP and browser
   proof, and safe override fixtures.
2. #859 owns UI-neutral shell actions and focus/history/announcement handoff.
3. #860 owns explicit loader/integration behavior and the ChirpUI compatibility
   migration.
4. #863 owns the modular scaffold, representative typed components, named-block
   page proof, docs, examples, and release collateral.

Acceptance #856: decision collateral; no behavioral test until implementation
children.
