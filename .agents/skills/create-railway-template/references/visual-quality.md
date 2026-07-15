# Chirp template visual quality

Treat each marketplace template as a small product, not a framework demo with renamed copy.

## Art direction

- Start from one product-specific visual premise: signal console, editorial board, operations ledger, community room, or another metaphor rooted in the task.
- Create family resemblance through craft, typography, spacing discipline, and a small Chirp attribution. Do not make every template share the same hero, gradient, card stack, or purple palette.
- Define named CSS tokens for ink, paper, surfaces, borders, accents, status colors, radii, and shadows. Use them consistently.
- Prefer a deliberate type hierarchy with readable body text and restrained display typography. Avoid oversized headings that push the application below the fold.
- Use motion only when it communicates state. Respect `prefers-reduced-motion`.

## Information hierarchy

- Put the route's primary job first. Inbox routes show captures; detail routes show details; admin routes show controls.
- Separate marketing or onboarding composition from authenticated utility composition.
- Keep one primary action per region and use status color semantically.
- Design empty, loading, error, locked, and populated states—not only the ideal screenshot.
- Make layouts usable at 320 CSS pixels and resilient to long paths, headers, names, and translated copy.

## CSS implementation

- Keep a small template's styles in one discoverable `styles.css`; split only when the product has real component boundaries.
- Order CSS by tokens, reset/base, layout, components, states, utilities, then responsive and motion preferences.
- Use semantic role names such as `.capture-row`, `.detail-card`, and `.empty-state`; avoid names tied only to color or position.
- Prefer classes and low-specificity selectors. Avoid element-ID styling, deep descendant chains, and `!important`.
- Express hover, focus, disabled, error, success, and live states deliberately. Do not make color the only state cue.
- Keep inline styles out of templates so the content security policy can remain strict and visual changes stay reviewable.
- Test narrow viewports, keyboard focus, zoom, long unbroken values, and reduced motion before capturing marketplace imagery.

## Accessibility and interaction

- Use semantic landmarks, headings, labels, and visible keyboard focus.
- Maintain WCAG AA contrast for text and controls.
- Give icon-only controls accessible names and keep tap targets at least 44 CSS pixels where practical.
- Preserve no-JavaScript form behavior; enhance with htmx rather than replacing the HTML path.

## Favicon contract

- Ship `favicon.svg` at minimum. Add PNG or ICO fallbacks only when the audience requires legacy support.
- Use a simple silhouette that survives at 16×16 pixels; avoid words, thin strokes, and screenshot crops.
- Draw from the product's mark and shipped color tokens. Include an SVG `<title>`.
- Link it from every full-page shell with `<link rel="icon" href="/favicon.svg" type="image/svg+xml">`.
- Serve it at `/favicon.svg` with `image/svg+xml`, include it in asset and catalog checks, and verify `200` in tests and the deployed smoke.
- Inspect the browser tab in both light and dark browser chrome; the mark must remain recognizable without relying on transparency alone.

## Marketplace imagery

- Show the real populated application at a representative desktop viewport.
- Avoid secrets, customer names, private endpoints, or internal metrics.
- Use a legible crop with the core workflow visible; do not let a decorative hero occupy most of the card.
- Keep the marketplace image, live demo, README, and current release visually consistent.
