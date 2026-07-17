# RFC 025: App-Owned UI, Template Roles, And Theme Ownership

**Status:** Accepted for implementation; this RFC changes no runtime behavior
**Issue:** [#862](https://github.com/lbliii/chirp/issues/862)
**Parent:** [#856](https://github.com/lbliii/chirp/issues/856)
**Related:** [#858](https://github.com/lbliii/chirp/issues/858), [#859](https://github.com/lbliii/chirp/issues/859), [#860](https://github.com/lbliii/chirp/issues/860), [#863](https://github.com/lbliii/chirp/issues/863), RFC 017
**Created:** 2026-07-17

## 1. Context

Chirp's durable UI contract is server-rendered HTML selected through typed return
values and one template's named blocks. It is not a design system. The current
default scaffold and template environment blur that boundary in two ways:

- `chirp new` changes its output when `chirp_ui` happens to be importable; and
- the template environment discovers chirp-ui templates and helpers from package
  presence rather than an explicit application integration.

That ambient behavior makes the same application configuration produce different
templates, filters, globals, and generated files on different machines. It also
makes it difficult for a generated application to own its visual identity without
first understanding which styling and rendering behavior belongs to ChirpUI.

The replacement must keep Chirp's named-block architecture, Kida's
framework-neutral component model, and chirp-ui as an explicit compatibility
option. It must not move a design system into Chirp under a different name.

This RFC freezes the ownership and authoring boundaries. The implementation is
split across issues #858, #859, #860, and #863 so public CLI behavior, template
loading, theme behavior, and shell handoff contracts can each receive focused
proof.

## 2. Decision summary

A generated Chirp application owns its templates, components, product patterns,
CSS, theme values, and visual identity from the moment it is created.

Chirp owns:

- typed render intent and the full-page/fragment/OOB/Suspense/streaming/SSE
  negotiation that follows from it;
- filesystem-route and named-block contracts;
- generic CSP, focus, history, announcement, OOB transport, and shell-action
  infrastructure;
- explicit template and component integration points; and
- diagnostics for framework contracts that Chirp can prove.

Kida owns the framework-neutral component language, typed props and slots,
discovery primitives, source locations, and component validation.

Applications own:

- layout composition and route-page markup;
- the decision to extract reusable Kida components or product patterns;
- semantic tokens, component CSS, page CSS, theme values, and brand assets;
- theme controls and product-specific client interactions; and
- accessibility and visual quality beyond the generic behavior Chirp can prove.

ChirpUI remains an optional, explicit compatibility integration during the
migration window. Merely installing it must not change generated output or a
template environment.

## 3. Template roles

The scaffold should teach five roles. The roles are stable even when an
application chooses different directory names.

### 3.1 Layouts

Layouts own document and shell structure: `<html>`, metadata, global assets,
landmarks, navigation chrome, and the outlet into which route content composes.
They may expose named extension points, but they do not own route-specific data or
duplicate a route's response blocks.

### 3.2 Route pages

Route pages own one URL's visible composition and remain the source of truth for
every response posture. Their named blocks serve full-page, plain, htmx fragment,
OOB, Suspense, streaming HTML, and SSE paths as applicable.

An application must not create a sibling HTMX-partials tree that restates route
markup. A request may select a named block, but it does not select a second view
model or a parallel template architecture. Missing required blocks continue to
fail loud.

### 3.3 Reusable Kida components

Components are reusable UI definitions with meaningful props or slots. They own
local structure and accessibility behavior, not routes, application state,
transport, or page-level block selection. Component grouping such as
`primitives/`, `controls/`, `feedback/`, and `chrome/` is an authoring aid rather
than a Chirp runtime taxonomy.

### 3.4 Product patterns

Patterns compose components and markup into product-specific units such as an
issue row, search result, billing summary, or activity panel. A pattern may know
the product vocabulary and expected slots. It is not promoted to a universal
primitive merely because two pages currently use it.

Patterns do not become a response surface. The owning route page still declares
the named blocks selected by Chirp.

### 3.5 Private partials

Private partials are rare, context-bound implementation details used to make a
single layout, page, component, or pattern readable. A partial may depend on its
caller's context and therefore must be visibly private, for example under
`_partials/` or with a leading underscore.

A partial is not the default reuse mechanism, a typed component substitute, or a
separate fragment response. If another owner needs it or its inputs matter, it
should become a component or pattern.

## 4. Scaffold convention versus framework contract

The proposed generated shape is:

```text
pages/
  _layout.html
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
static/css/
  tokens.css
  base.css
  components.css
  patterns.css
  pages.css
static/js/
  theme.js
  interactions.js
```

The boundary is explicit:

| Surface | Contract status |
| --- | --- |
| Configured template root and component roots | Chirp application configuration contract |
| Filesystem-route discovery, including the accepted `page.py`, `page.html`, and `_layout.html` meanings | Chirp framework contract |
| Named blocks selected by typed return values | Chirp framework contract |
| Kida component definitions, props, slots, discovery facts, and validation | Kida contract |
| `templates/layouts/`, `components/`, `patterns/`, and `_partials/` names | Scaffold convention |
| Component category directory names | Scaffold convention |
| `tokens.css`, `base.css`, `components.css`, `patterns.css`, and `pages.css` names and layering | Scaffold convention |
| `theme.js` and `interactions.js` names | Scaffold convention |

Applications may rename, combine, or split convention-only files without opting
out of Chirp behavior. Future diagnostics must not report an error solely because
an application uses a different convention-only name.

Component and template roots must be explicit application input. Kida should not
gain Chirp-specific meanings for these directory names.

## 5. Extraction heuristics

Generated guidance should favor the smallest boundary that removes meaningful
duplication or gives a concept a stable interface.

Keep markup inline when it:

- appears once and is short enough to understand with its page;
- depends heavily on one route's context;
- has no independently testable behavior or accessibility contract; and
- would produce a pass-through wrapper whose props simply repeat local names.

Extract a Kida component when at least one of these is true:

- the same semantic unit appears in multiple owners;
- props or slots form a useful, stable interface;
- accessibility behavior should be implemented and tested once;
- local structure or variants obscure the page's composition; or
- independent discovery and validation materially improve authoring.

Extract a product pattern when the unit combines several components or repeated
markup around product vocabulary, state, and actions but is not a general-purpose
primitive.

Use a private partial only when the markup is intentionally coupled to one owner
and introducing a typed interface would add ceremony without a reusable contract.

Do not extract solely to reduce line count. Do not make components responsible for
route registration, return-type choice, target negotiation, or named response
blocks.

## 6. Styling and theme ownership

CSS is ordinary app-owned source. Semantic custom properties are the alignment
layer, but Chirp does not define their names, ship a runtime token registry,
generate CSS, expose a CSS-in-Python API, or require a frontend build tool.

The generated scaffold should demonstrate separate token, base, component,
pattern, and page layers. Those files are copied application source, not package
assets whose values change on a Chirp upgrade.

The root theme contract uses:

- `data-theme="light"`, `data-theme="dark"`, or `data-theme="system"` for the
  user's preference;
- optional `data-skin` for an application-defined visual variant; and
- optional `data-density` for an application-defined spacing/control density.

The values of `data-skin` and `data-density` are not framework enumerations.
Applications define and validate their own allowlists.

### 6.1 Persistence and authority

Theme preference has one server-readable authority for each posture:

1. For an authenticated user, the server-side account preference is canonical so
   it follows the user across browsers.
2. For an anonymous user, a same-site preference cookie is canonical so the
   server can render the correct root attribute before CSS is applied.
3. Local storage is not a second source of truth. An application may use it as a
   same-browser cache or cross-tab notification mechanism, but it must reconcile
   to the server/account or cookie value and must not make navigation output
   depend on an unreadable client-only preference.

The default is `system` when no preference exists. A no-JavaScript form submission
must be able to update the server-readable preference and redirect to a correctly
themed full page. Script may enhance the control by updating the root attribute
immediately and then persisting through the same server path.

HTMX swaps do not replace or recompute the root theme attributes. Full navigation
renders them from the server-readable preference.

### 6.2 First paint and system changes

The minimum pre-paint inline script is **none**.

The server renders the selected `data-theme` value on `<html>`. App-owned CSS
handles `data-theme="system"` with `prefers-color-scheme`, so the browser can choose
the system palette before first paint without executable inline content. This is
compatible with a strict CSP and works when JavaScript is disabled.

An external, app-owned `theme.js` may listen for system preference changes while
`data-theme="system"` is active, synchronize control state, update other tabs, and
enhance persistence. It must work under the application's script CSP without
requiring `unsafe-inline` or Alpine. The CSS result must remain correct if the
script is blocked.

### 6.3 Tenant and user overrides

Arbitrary user-controlled CSS, selectors, property names, or style text must not
be rendered into a page.

Prefer trusted, application-defined token sets selected by validated
`data-skin`/`data-density` enum values. HTML escaping is required but is not a
substitute for allowlist validation.

When a product genuinely supports per-tenant token values:

- accept only fixed property names owned by the application;
- parse each value according to a narrow type and range or an explicit enum;
- reject CSS syntax outside that grammar rather than trying to escape it;
- prefer a generated, content-addressed stylesheet served under the application's
  style policy; and
- if request-specific inline CSS is unavoidable, render a fixed selector and
  fixed property names in a nonce-authorized `<style>` element using only the
  validated values.

Chirp's CSP infrastructure may provide the nonce. It does not become a theme
value validator or tenant-design API.

## 7. Chirp-owned browser infrastructure

Chirp retains UI-neutral infrastructure needed for hypermedia correctness:

- CSP nonce and policy plumbing;
- focus preservation or explicit focus handoff after swaps;
- document title and history handoff;
- announcements and live-region transport where the application requests them;
- OOB transport for shell-level state; and
- generic shell actions with safe, style-neutral HTML or an explicit application
  renderer.

These contracts must remain compatible with full-page and htmx paths and must not
prescribe component class names, tokens, theme values, or a visual style. RFC 017's
accepted focus and live-region families remain the accessibility input; issue
#859 must not invent a competing policy.

Product interactions, component behavior, theme controls, and brand-specific
shell rendering remain application concerns.

## 8. `chirp check` boundary

`chirp check` validates facts that follow from explicit framework contracts and
can be proved from the compiled application, including named-block resolution,
render targets, OOB wiring, route/template relationships, and explicit integration
configuration.

Future implementation may report actionable diagnostics when:

- an explicit component root or package integration cannot be loaded;
- an explicit theme or handoff declaration has an invalid value or unresolved
  target;
- an application still relies on a detectable ambient chirp-ui assumption; or
- generated security/accessibility fixtures violate an existing contract.

It may advise, at `INFO` or in documentation, about scaffold conventions and
extraction heuristics. It must not emit an error because an application renames a
convention-only directory or CSS file, chooses different tokens, keeps sensible
markup inline, or has a visual style Chirp cannot evaluate.

This RFC adds no check category and changes no severity. Each proposed diagnostic
requires focused false-positive evidence and the normal severity check-in before
implementation.

## 9. ChirpUI compatibility boundary

During migration:

- `chirp-ui` remains an optional extra;
- an explicit compatibility integration such as the existing
  `use_chirp_ui(app)` path may register ChirpUI templates, filters, globals, and
  assets;
- `chirp new` produces the same default files whether or not chirp-ui is installed;
- a template environment produces the same loaders, filters, and globals for the
  same explicit application configuration whether or not chirp-ui is installed;
- existing explicitly integrated ChirpUI applications continue to work through a
  documented migration window; and
- generic shell actions adapt to the UI-neutral Chirp contract rather than Chirp
  importing a ChirpUI renderer.

Issue #860 removes ambient discovery but does not remove the explicit compatibility
integration. Removing the optional extra, renaming its public activation surface,
or migrating existing applications requires a later approved retirement plan.

## 10. Downstream impact review

| Area | Frozen impact |
| --- | --- |
| Templating | Preserve one-template/named-block rendering. Load component roots and package integrations explicitly. Do not add a partial response system. |
| CLI | Make generation deterministic. Teach the five template roles and app-owned CSS without detecting installed packages. Move every public flag and generated default with focused scaffold tests and documentation. |
| Security | Keep the zero-inline-script baseline, strict CSP compatibility, server-readable preference, and validated tenant overrides. Do not broaden script or style policy to make theming convenient. |
| Accessibility | Generated controls and representative components need focus visibility, forced-colors, reduced-motion, keyboard, naming, and live-region proof where relevant. Theme changes must not steal focus or depend on color alone. |
| Kida | Consume framework-neutral typed component, prop, slot, discovery, validation, and source-location contracts. Do not add Chirp directory semantics to Kida or make Kida select HTTP response blocks. |
| chirp-ui | Keep only an explicit compatibility path. Package presence alone must have no effect. Adapt shell behavior to UI-neutral infrastructure until a separate retirement decision. |

## 11. Rejected alternatives

| Alternative | Reason rejected |
| --- | --- |
| Move ChirpUI components into Chirp | It turns the framework into a design-system owner and makes the optional dependency effectively mandatory. |
| Keep package-presence auto-detection | Identical application configuration would continue to produce environment-dependent behavior. |
| Build a Chirp token registry or manifest | Ordinary app-owned CSS already supplies the needed alignment layer without runtime state or a new public API. |
| Require a frontend compiler | It raises the scaffold floor and conflicts with the server-rendered, copyable-source posture. |
| Use local storage as the only theme preference | The server cannot render the correct first response, and no-JavaScript navigation loses the preference. |
| Require an inline pre-paint script | Server-rendered root state plus CSS media queries provides the supported first-paint floor without weakening CSP. |
| Create dedicated HTMX partial templates | It duplicates the route view and breaks the one-template/named-block architecture. |
| Treat every repeated element as a component | It produces pass-through abstractions without stable semantics, behavior, or accessibility value. |
| Make `chirp check` enforce scaffold filenames | Convention-only names are not runtime correctness contracts. |

## 12. Non-goals

This decision does not:

- choose a visual style or define a canonical token vocabulary;
- design a token compiler, CSS generator, runtime theme registry, or CSS-in-Python
  model;
- move chirp-ui into Chirp or remove the compatibility extra;
- design migrations for existing applications;
- change AppConfig, return types, render plans, block discovery, or check
  severities;
- introduce a SPA, JSON view model, or mandatory frontend build; or
- implement the scaffold, theme control, explicit component loader, or shell
  renderer.

Those implementation changes remain in #858, #859, #860, and #863 and must carry
their own focused tests, documentation, compatibility receipts, and changelog
decisions.

## 13. Acceptance receipt

This RFC closes the ownership questions required by #862 while preserving the
parent architecture:

- layouts, route pages, reusable components, product patterns, and private
  partials have distinct roles;
- route pages and named blocks remain the only response surface;
- extraction guidance favors stable semantic interfaces over line-count wrappers;
- applications own tokens, CSS, theme values, and visual identity;
- root theme state, persistence authority, CSP-safe first paint, and validated
  tenant overrides are specified;
- Chirp-owned browser infrastructure is UI-neutral;
- `chirp check` validation is separated from convention advice; and
- chirp-ui has an explicit, bounded compatibility path.

Acceptance #862: decision collateral only; behavioral proof belongs to the
implementation children.
