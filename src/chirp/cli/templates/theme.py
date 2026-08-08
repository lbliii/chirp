"""App-owned theme + CSS layer templates for ``chirp new`` (RFC 025 / #858)."""

# Theme preference helpers written next to generated app.py.
THEME_PY = '''\
"""App-owned theme preference helpers.

Chirp does not own token names or a theme registry. This module is ordinary
application source: cookie-backed preference for anonymous users, validated
allowlist values, and a redirect response that sets the cookie.
"""

from __future__ import annotations

from chirp.http.request import Request
from chirp.http.response import Response

THEME_COOKIE = "chirp_theme"
THEMES = frozenset({"light", "dark", "system"})
DEFAULT_THEME = "system"
# Optional extension points — apps define their own allowlists.
SKINS: frozenset[str] = frozenset()
DENSITIES: frozenset[str] = frozenset()


def normalize_theme(value: str | None) -> str:
    """Return a validated theme preference or the default."""
    if value in THEMES:
        return value
    return DEFAULT_THEME


def normalize_optional(value: str | None, allowed: frozenset[str]) -> str | None:
    """Return an allowlisted optional attribute value, else None."""
    if value and value in allowed:
        return value
    return None


def read_theme(request: Request) -> str:
    """Read the server-readable theme preference (cookie), defaulting to system."""
    return normalize_theme(request.cookies.get(THEME_COOKIE))


def theme_redirect(
    next_url: str,
    theme: str,
    *,
    secure: bool = False,
    skin: str | None = None,
    density: str | None = None,
) -> Response:
    """303 redirect that persists theme (and optional skin/density) cookies."""
    theme = normalize_theme(theme)
    response = (
        Response()
        .with_status(303)
        .with_header("Location", next_url)
        .with_cookie(
            THEME_COOKIE,
            theme,
            max_age=60 * 60 * 24 * 365,
            httponly=True,
            samesite="lax",
            secure=secure,
        )
    )
    skin = normalize_optional(skin, SKINS)
    density = normalize_optional(density, DENSITIES)
    if skin is not None:
        response = response.with_cookie(
            "chirp_skin",
            skin,
            max_age=60 * 60 * 24 * 365,
            httponly=True,
            samesite="lax",
            secure=secure,
        )
    if density is not None:
        response = response.with_cookie(
            "chirp_density",
            density,
            max_age=60 * 60 * 24 * 365,
            httponly=True,
            samesite="lax",
            secure=secure,
        )
    return response
'''

V2_CONTEXT_PY = '''\
"""Root context — theme preference available to every layout render."""

from theme import read_theme


def context(request) -> dict:
    return {"theme": read_theme(request), "current_path": request.path}
'''

TOKENS_CSS = """\
/* App-owned semantic tokens (scaffold convention — rename freely).
 *
 * Layers: tokens → base → components → patterns → pages.
 * Theme selection uses root data-theme=light|dark|system.
 * Optional data-skin / data-density are extension points you define.
 */

:root,
[data-theme="light"] {
  color-scheme: light;

  --color-bg: #f8fafc;
  --color-bg-elevated: #ffffff;
  --color-fg: #0f172a;
  --color-fg-muted: #475569;
  --color-border: #cbd5e1;
  --color-accent: #2563eb;
  --color-accent-fg: #ffffff;
  --color-danger: #b91c1c;
  --color-focus: #2563eb;

  --font-sans: system-ui, -apple-system, "Segoe UI", sans-serif;
  --font-mono: ui-monospace, "SFMono-Regular", Menlo, Consolas, monospace;
  --font-size-sm: 0.875rem;
  --font-size-md: 1rem;
  --font-size-lg: 1.25rem;
  --font-size-xl: 1.75rem;
  --line-height: 1.5;
  --font-weight-normal: 400;
  --font-weight-semibold: 600;

  --space-1: 0.25rem;
  --space-2: 0.5rem;
  --space-3: 0.75rem;
  --space-4: 1rem;
  --space-6: 1.5rem;
  --space-8: 2rem;

  --radius-sm: 0.375rem;
  --radius-md: 0.5rem;
  --radius-lg: 0.75rem;

  --shadow-sm: 0 1px 2px rgb(15 23 42 / 0.08);
  --shadow-md: 0 4px 12px rgb(15 23 42 / 0.12);

  --motion-fast: 120ms;
  --motion-normal: 200ms;
  --ease-standard: cubic-bezier(0.2, 0, 0, 1);

  --focus-ring-width: 2px;
  --focus-ring-offset: 2px;

  --layout-max: 40rem;
  --layout-gutter: var(--space-4);
}

[data-theme="dark"] {
  color-scheme: dark;

  --color-bg: #0f172a;
  --color-bg-elevated: #1e293b;
  --color-fg: #e2e8f0;
  --color-fg-muted: #94a3b8;
  --color-border: #334155;
  --color-accent: #3b82f6;
  --color-accent-fg: #ffffff;
  --color-danger: #f87171;
  --color-focus: #60a5fa;

  --shadow-sm: 0 1px 2px rgb(0 0 0 / 0.35);
  --shadow-md: 0 4px 12px rgb(0 0 0 / 0.45);
}

@media (prefers-color-scheme: light) {
  [data-theme="system"] {
    color-scheme: light;

    --color-bg: #f8fafc;
    --color-bg-elevated: #ffffff;
    --color-fg: #0f172a;
    --color-fg-muted: #475569;
    --color-border: #cbd5e1;
    --color-accent: #2563eb;
    --color-accent-fg: #ffffff;
    --color-danger: #b91c1c;
    --color-focus: #2563eb;

    --shadow-sm: 0 1px 2px rgb(15 23 42 / 0.08);
    --shadow-md: 0 4px 12px rgb(15 23 42 / 0.12);
  }
}

@media (prefers-color-scheme: dark) {
  [data-theme="system"] {
    color-scheme: dark;

    --color-bg: #0f172a;
    --color-bg-elevated: #1e293b;
    --color-fg: #e2e8f0;
    --color-fg-muted: #94a3b8;
    --color-border: #334155;
    --color-accent: #3b82f6;
    --color-accent-fg: #ffffff;
    --color-danger: #f87171;
    --color-focus: #60a5fa;

    --shadow-sm: 0 1px 2px rgb(0 0 0 / 0.35);
    --shadow-md: 0 4px 12px rgb(0 0 0 / 0.45);
  }
}

/* Optional skin / density hooks — define allowlists in theme.py before using. */
[data-density="compact"] {
  --space-4: 0.75rem;
  --space-6: 1rem;
  --space-8: 1.25rem;
}

@media (prefers-reduced-motion: reduce) {
  :root {
    --motion-fast: 0ms;
    --motion-normal: 0ms;
  }
}
"""

BASE_CSS = """\
/* Reset and element defaults — consume tokens only. */

*,
*::before,
*::after {
  box-sizing: border-box;
}

* {
  margin: 0;
}

html {
  font-family: var(--font-sans);
  font-size: var(--font-size-md);
  line-height: var(--line-height);
  background: var(--color-bg);
  color: var(--color-fg);
}

body {
  min-height: 100vh;
  max-width: var(--layout-max);
  margin: 0 auto;
  padding: var(--space-8) var(--layout-gutter);
}

a {
  color: var(--color-accent);
  text-decoration: none;
}

a:hover {
  text-decoration: underline;
}

:focus-visible {
  outline: var(--focus-ring-width) solid var(--color-focus);
  outline-offset: var(--focus-ring-offset);
}

@media (forced-colors: active) {
  :focus-visible {
    outline: 3px solid CanvasText;
  }
}

.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border: 0;
}

label {
  display: block;
  margin-top: var(--space-3);
  font-weight: var(--font-weight-semibold);
}

input {
  display: block;
  width: 100%;
  margin-top: var(--space-1);
  padding: var(--space-2) var(--space-3);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  background: var(--color-bg-elevated);
  color: var(--color-fg);
}

button,
.theme-control button {
  margin-top: var(--space-4);
  padding: var(--space-2) var(--space-4);
  border: none;
  border-radius: var(--radius-md);
  background: var(--color-accent);
  color: var(--color-accent-fg);
  cursor: pointer;
  font: inherit;
}

button:hover {
  filter: brightness(1.05);
}

small {
  color: var(--color-fg-muted);
}

.error {
  color: var(--color-danger);
  margin-bottom: var(--space-4);
  font-size: var(--font-size-sm);
}
"""

COMPONENTS_CSS = """\
/* Reusable component styles (pair with templates/components/). */

.panel {
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  padding: var(--space-4);
  background: var(--color-bg-elevated);
  box-shadow: var(--shadow-sm);
}

.panel__body {
  display: grid;
  gap: var(--space-3);
  margin-top: var(--space-3);
}

.status {
  display: inline-flex;
  align-items: center;
  border-radius: 999px;
  padding: var(--space-1) var(--space-3);
  background: color-mix(in srgb, var(--color-accent) 18%, transparent);
  color: var(--color-fg);
}

.theme-control {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-2);
  margin: 0;
}

.theme-control fieldset {
  border: 0;
  padding: 0;
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-3);
}

.theme-control label {
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
  margin: 0;
  font-weight: var(--font-weight-normal);
  font-size: var(--font-size-sm);
  color: var(--color-fg-muted);
}

.theme-control input {
  width: auto;
  margin: 0;
  display: inline;
}

.theme-control button {
  margin-top: 0;
  padding: var(--space-1) var(--space-3);
  font-size: var(--font-size-sm);
  background: transparent;
  color: var(--color-fg-muted);
  border: 1px solid var(--color-border);
}

.theme-control button:hover {
  color: var(--color-fg);
  filter: none;
}
"""

PATTERNS_CSS = """\
/* Product patterns (pair with templates/patterns/). */

.account-summary {
  display: grid;
  gap: var(--space-2);
}
"""

PAGES_CSS = """\
/* Route-specific page styles. */

.app-nav {
  display: flex;
  align-items: center;
  gap: var(--space-4);
  flex-wrap: wrap;
  margin-bottom: var(--space-8);
  padding-bottom: var(--space-4);
  border-bottom: 1px solid var(--color-border);
}

.app-nav a {
  color: var(--color-fg-muted);
  text-decoration: none;
}

.app-nav a:hover {
  color: var(--color-fg);
}

.app-nav form {
  margin-left: auto;
}

.app-nav .theme-control {
  margin-left: auto;
}

h1 {
  font-size: var(--font-size-xl);
  font-weight: var(--font-weight-semibold);
  margin-bottom: var(--space-4);
}
"""

THEME_JS = """\
/* Progressive theme enhancement — no Alpine, no inline script.
 *
 * First paint is server-rendered (data-theme on <html>) plus CSS
 * prefers-color-scheme for data-theme=system. This file only enhances
 * the control and reacts to system preference changes.
 */
(function () {
  var root = document.documentElement;
  var form = document.querySelector("[data-theme-control]");
  if (!form) return;

  function current() {
    return root.getAttribute("data-theme") || "system";
  }

  function apply(theme) {
    root.setAttribute("data-theme", theme);
    var input = form.querySelector('input[name="theme"][value="' + theme + '"]');
    if (input) input.checked = true;
  }

  form.addEventListener("change", function (event) {
    var target = event.target;
    if (!target || target.name !== "theme") return;
    apply(target.value);
  });

  var media = window.matchMedia("(prefers-color-scheme: dark)");
  function onSystemChange() {
    if (current() === "system") {
      // Force style recalc for listeners; attribute stays "system".
      root.setAttribute("data-theme", "system");
    }
  }
  if (typeof media.addEventListener === "function") {
    media.addEventListener("change", onSystemChange);
  } else if (typeof media.addListener === "function") {
    media.addListener(onSystemChange);
  }

  window.addEventListener("storage", function (event) {
    if (event.key === "chirp-theme-sync" && event.newValue) {
      apply(event.newValue);
    }
  });

  form.addEventListener("submit", function () {
    try {
      localStorage.setItem("chirp-theme-sync", current());
    } catch (err) {
      /* ignore quota / private mode */
    }
  });
})();
"""

INTERACTIONS_JS = """\
/* App-owned progressive interactions. Keep CSP-compatible (no inline). */
"""

THEME_CONTROL_HTML = """\
    <form method="post" action="/theme" class="theme-control" data-theme-control
          hx-boost="false">
        {{ csrf_field() }}
        <input type="hidden" name="next" value="{{ current_path }}">
        <fieldset>
            <legend class="sr-only">Color theme</legend>
            <label><input type="radio" name="theme" value="light"{% if theme == "light" %} checked{% end %}> Light</label>
            <label><input type="radio" name="theme" value="dark"{% if theme == "dark" %} checked{% end %}> Dark</label>
            <label><input type="radio" name="theme" value="system"{% if theme == "system" %} checked{% end %}> System</label>
        </fieldset>
        <button type="submit">Apply theme</button>
    </form>
"""
