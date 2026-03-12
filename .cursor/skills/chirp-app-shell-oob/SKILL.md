---
name: chirp-app-shell-oob
description: Build app shells with AST-driven OOB updates for sidebar, breadcrumbs, and title. Use when building Chirp + ChirpUI apps with HTMX navigation.
---

# Chirp App Shell with AST-Powered OOB Updates

Pattern for building HTMX-navigable apps where sidebar active state, breadcrumbs, and document title update automatically on boosted navigation — driven by Kida's AST metadata, not hard-coded logic.

## How It Works

1. **Root layout** declares OOB regions (`breadcrumbs_oob`, `sidebar_oob`, `title_oob`) alongside the full app shell
2. **Page handlers** provide `current_path`, `page_title`, and `breadcrumb_items` in their context
3. **Chirp's render pipeline** uses Kida's `template_metadata()` to discover OOB regions at build time
4. On **boosted navigation** (HTMX `hx-boost`), Chirp renders the page fragment AND the OOB regions as `hx-swap-oob` updates
5. On **full page load**, the entire layout renders normally (OOB regions are suppressed)

## Regions: Zero-Duplication Pattern (RFC: kida-regions)

Kida's `{% region %}` construct compiles to BOTH a block (for `render_block`) AND a callable (for `{{ name(args) }}`). Use regions instead of separate blocks + defs:

- **One definition** serves both app shell slots and OOB `render_block()`
- **Parameters** make regions self-contained: `{% region sidebar_oob(current_path="/") %}...{% end %}`
- **Callable**: `{{ sidebar_oob(current_path=current_path | default("/")) }}` in app shell slots
- **Renderable**: `render_block("sidebar_oob", current_path=...)` for OOB updates

## Root Layout Template (Regions Pattern)

```html
{# target: body #}
<!DOCTYPE html>
<html lang="en">
<head>
  <!-- ... head content ... -->
  <title id="chirpui-document-title">{{ page_title | default("My App") }}</title>
</head>
<body>
{% from "chirpui/app_shell.html" import app_shell %}
{% from "chirpui/sidebar.html" import sidebar, sidebar_section, sidebar_link %}
{% from "chirpui/breadcrumbs.html" import breadcrumbs %}
{% from "chirpui/theme_toggle.html" import theme_toggle %}

{# Regions: one definition for both app shell slots AND OOB render_block #}

{% region breadcrumbs_oob(breadcrumb_items=[{"label":"Home","href":"/"}]) %}
{{ breadcrumbs(breadcrumb_items) }}
{% end %}

{% region title_oob(page_title="My App") %}
<title id="chirpui-document-title" hx-swap-oob="true">{{ page_title }}</title>
{% end %}

{% region sidebar_oob(current_path="/") %}
{% call sidebar() %}
  {% call sidebar_section("Pages") %}
    {{ sidebar_link("/", "Home", icon="home", active=current_path == "/") }}
    {{ sidebar_link("/settings", "Settings", icon="settings", active=current_path.startswith("/settings")) }}
  {% end %}
{% end %}
{% end %}

{% call app_shell(brand="My App", sidebar_collapsible=true) %}
  {% slot topbar %}
  {{ breadcrumbs_oob(breadcrumb_items=breadcrumb_items | default([{"label":"Home","href":"/"}])) }}
  {% end %}
  {% slot topbar_end %}
  {{ theme_toggle() }}
  {% end %}
  {% slot sidebar %}
  {{ sidebar_oob(current_path=current_path | default("/")) }}
  {% end %}
  {% block content %}{% end %}
{% end %}
</body>
</html>
```

### Why `{# target: body #}`?

The `target` annotation tells Chirp where HTMX should swap content. With `body`, the entire `<body>` is the swap target for full page loads, and the OOB regions update specific DOM areas during fragment navigation. Using `main` would skip OOB region rendering entirely.

## Page Handler Pattern

Every handler must provide three context keys for OOB updates to work:

```python
from chirp import Request
from chirp.templating.composition import PageComposition


def get(request: Request) -> PageComposition:
    return PageComposition(
        template="settings/page.html",
        context={
            "current_path": request.path,
            "page_title": "Settings",
            "breadcrumb_items": [
                {"label": "Home", "href": "/"},
                {"label": "Settings"},
            ],
            # ... page-specific context ...
        },
    )
```

With ChirpUI, `fragment_block` and `page_block` are optional — the FragmentTargetRegistry resolves from `HX-Target` (`#main`, `#page-root`, `#page-content-inner`).

| Key | Purpose | Used by |
|-----|---------|---------|
| `current_path` | Sidebar active state detection | `sidebar_oob` block |
| `page_title` | Document `<title>` update | `title_oob` block |
| `breadcrumb_items` | Breadcrumb trail | `breadcrumbs_oob` block |

For dynamic pages, use the entity name:

```python
def get(request: Request, skill: Skill) -> PageComposition:
    return PageComposition(
        template="skill/{name}/page.html",
        context={
            "current_path": request.path,
            "page_title": skill.name,
            "breadcrumb_items": [
                {"label": "Home", "href": "/"},
                {"label": "Skills", "href": "/skills"},
                {"label": skill.name},
            ],
        },
    )
```

## Page Template Pattern

Page templates define two nested blocks:

```html
{% block page_root %}
{% block page_content %}
<div style="padding: 2rem;">
  <h1>Settings</h1>
  <p>Page content here.</p>
</div>
{% end %}
{% end %}
```

- `page_root` — outer block for full page composition and sidebar nav (`hx-target="#main"`)
- `page_root_inner` — inner block for tab clicks (`hx-target="#page-root"`)
- `page_content` — narrow block for content-only swaps (`hx-target="#page-content-inner"`)

ChirpUI registers these via `use_chirp_ui()`. `main` and `page-root` have `triggers_shell_update=True` so shell_actions (topbar, breadcrumbs, title) update on sidebar and tab clicks; `page-content-inner` has `triggers_shell_update=False` so narrow swaps don't update the shell. Custom targets: `app.register_fragment_target("id", fragment_block="...", triggers_shell_update=True)`.

## Context Cascade with _context.py

Use `_context.py` files for section-level shared context:

```python
# pages/settings/_context.py
def context() -> dict:
    return {
        "page_title": "Settings",
        "breadcrumb_items": [
            {"label": "Home", "href": "/"},
            {"label": "Settings"},
        ],
    }
```

Child pages override by providing the same keys in their handler context.

## AST-Driven Discovery (How Chirp Finds OOB Regions)

Chirp does not hard-code which blocks to render as OOB. Instead, it uses Kida's `template_metadata()`:

1. `build_layout_contract()` calls `template_metadata()` on the root layout
2. Blocks/regions named `*_oob` are identified as OOB candidates
3. Each block's `cache_scope` and `depends_on` metadata (from Kida's AST) determines rendering behavior:
   - `cache_scope: "site"` → skip (static, doesn't change per page)
   - `depends_on: {"page_title"}` → skip if `page_title` not in context
4. The `LayoutContract` is cached per template for efficiency

This means adding new OOB regions requires only:
1. Add a `{% region new_region_oob(params) %}...{% end %}` to the layout
2. Map the region name to a target DOM ID in `_OOB_TARGET_MAP`

## Checklist

- [ ] Root layout uses `{# target: body #}` (not `main`)
- [ ] Use `{% region name_oob(params) %}...{% end %}` for OOB regions (zero duplication)
- [ ] Call regions in app shell slots: `{{ name_oob(param=value | default(...)) }}`
- [ ] `{% from %}` imports are at template top level (compile-time, works everywhere)
- [ ] Every handler provides `current_path`, `page_title`, `breadcrumb_items`
- [ ] Page templates use `page_root` / `page_content` two-block pattern
- [ ] Region params (e.g. `current_path`) are used directly in the region body
