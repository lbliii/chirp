# RFC: First-Party Component Collection

**Status**: Draft  
**Date**: 2026-02-10  
**Scope**: Separate package — `chirp-ui` or ecosystem-named equivalent  
**Related**: Gap Analysis — Kida/Chirp Strategic Plan  
**Depends on**: Gap 1 RFC (Typed `{% def %}` parameters in Kida)

---

## Problem

Developers starting a Chirp app have no reusable UI components. Every project
builds cards, modals, tabs, dropdowns, and toasts from scratch using ad-hoc
`{% def %}` macros. FastHTML ships PicoCSS by default. Ludic has a full theme
system with responsive primitives. Chirp's examples use inline styles.

This is a barrier to adoption. A developer evaluating Chirp sees a bare
framework and must invest significant effort before they have a presentable
UI — even for a prototype.

### Evidence

**Examples use inline styles** (`examples/kanban/templates/base.html`):
Custom CSS is embedded in `<style>` tags per project.

**Components are per-project** (`examples/kanban/templates/components/`):
`_card.html`, `_badge.html`, `_column.html` — all project-specific, not
reusable across projects.

**No component distribution mechanism**: Kida has `PackageLoader`
(`src/kida/environment/loaders.py:321`) and `PrefixLoader` (line 249) that
could serve installed packages, but no first-party component package exists.

---

## Goals

1. A separate, installable package of reusable Kida `{% def %}` components.
2. Minimal, framework-agnostic CSS — not a design system.
3. Zero JavaScript — htmx-native interaction patterns only.
4. Importable via standard Kida syntax: `{% from "chirpui/card" import card %}`.
5. Fully typed if Gap 1 (typed `{% def %}`) is implemented.

### Non-Goals

- Design system (no opinionated colors, fonts, or spacing tokens).
- CSS framework (not Bootstrap, not Tailwind, not Pico).
- JavaScript components (no Alpine, no Stimulus).
- Chirp core dependency (core stays minimal; this is `pip install chirp-ui`).

---

## Design

### Package Structure

```
chirp-ui/
├── pyproject.toml
├── src/
│   └── chirp_ui/
│       ├── __init__.py
│       └── templates/
│           ├── chirpui/
│           │   ├── card.html
│           │   ├── modal.html
│           │   ├── tabs.html
│           │   ├── dropdown.html
│           │   ├── toast.html
│           │   ├── table.html
│           │   ├── pagination.html
│           │   ├── alert.html
│           │   └── forms.html      # Extended form macros
│           └── chirpui.css          # Minimal structural CSS
└── tests/
```

### Component Design Principles

**1. Headless by default.** Components define structure and behavior, not
appearance. CSS classes are applied but styles are minimal:

```html
{# chirpui/card.html #}
{% def card(title=None, footer=None) %}
    <article class="chirpui-card">
        {% if title %}
            <header class="chirpui-card__header">{{ title }}</header>
        {% end %}
        <div class="chirpui-card__body">
            {% slot %}
        </div>
        {% if footer %}
            <footer class="chirpui-card__footer">{{ footer }}</footer>
        {% end %}
    </article>
{% end %}
```

**2. htmx-native.** Interactive components use htmx attributes, not JavaScript:

```html
{# chirpui/modal.html #}
{% def modal(id, title=None, size="medium") %}
    <dialog id="{{ id }}" class="chirpui-modal chirpui-modal--{{ size }}">
        {% if title %}
            <header class="chirpui-modal__header">
                <h2>{{ title }}</h2>
                <button class="chirpui-modal__close"
                        onclick="this.closest('dialog').close()">
                    &times;
                </button>
            </header>
        {% end %}
        <div class="chirpui-modal__body">
            {% slot %}
        </div>
    </dialog>
{% end %}

{% def modal_trigger(target, label="Open") %}
    <button class="chirpui-modal-trigger"
            onclick="document.getElementById('{{ target }}').showModal()">
        {{ label }}
    </button>
{% end %}
```

**3. Composable.** Components use `{% slot %}` for content injection and
nest freely:

```html
{% from "chirpui/card" import card %}
{% from "chirpui/table" import table, row %}

{% call card(title="Recent Orders") %}
    {% call table(headers=["ID", "Customer", "Total"]) %}
        {% for order in orders %}
            {{ row(order.id, order.customer, order.total) }}
        {% end %}
    {% end %}
{% end %}
```

**4. Customizable via CSS custom properties.** The minimal CSS uses custom
properties for the few structural values:

```css
/* chirpui.css */
.chirpui-card {
    border: 1px solid var(--chirpui-border, #e5e7eb);
    border-radius: var(--chirpui-radius, 0.5rem);
    overflow: hidden;
}

.chirpui-modal {
    max-width: var(--chirpui-modal-width, 32rem);
    border: 1px solid var(--chirpui-border, #e5e7eb);
    border-radius: var(--chirpui-radius, 0.5rem);
}
```

Users override these properties in their own CSS — no theming API, no
JavaScript config, just CSS.

### Loader Registration

When `chirp-ui` is installed, Chirp's environment setup auto-detects it and
adds a `PackageLoader`:

```python
# src/chirp/templating/integration.py

def create_environment(config: AppConfig, ...) -> kida.Environment:
    loaders = [FileSystemLoader(config.template_dir)]

    # Auto-detect chirp-ui if installed
    try:
        import chirp_ui
        loaders.append(PackageLoader("chirp_ui", "templates"))
    except ImportError:
        pass

    loader = ChoiceLoader(loaders)
    return kida.Environment(loader=loader, ...)
```

This means `{% from "chirpui/card" import card %}` works immediately after
`pip install chirp-ui` — no configuration needed.

### Component Catalog

Initial component set (v0.1):

| Component | File | Features |
|-----------|------|----------|
| **card** | `card.html` | Header, body (slot), footer, collapsible variant |
| **modal** | `modal.html` | Dialog-based, trigger button, close button |
| **tabs** | `tabs.html` | htmx-powered tab switching, active state |
| **dropdown** | `dropdown.html` | Native `<details>`-based, no JS |
| **toast** | `toast.html` | htmx OOB toast notifications |
| **table** | `table.html` | Responsive table with header, row, sortable |
| **pagination** | `pagination.html` | htmx-powered page navigation |
| **alert** | `alert.html` | Info, success, warning, error variants |
| **forms** | `forms.html` | Extended field macros (builds on Gap 3) |

---

## Testing Strategy

1. **Render tests**: Each component renders correct HTML with various inputs.
2. **Composition tests**: Components nest correctly (`card` inside `tabs`, etc.).
3. **CSS tests**: Structural CSS applies correct classes, custom properties work.
4. **Integration tests**: Components work in a Chirp app with htmx interactions.
5. **Accessibility tests**: Components use semantic HTML, ARIA where needed.

---

## Future Considerations

1. **Documentation site**: Live component preview with source code.
2. **Dark mode**: CSS custom properties make this trivial for users.
3. **Animation**: CSS-only transitions for modals, dropdowns.
4. **Typed components**: When Gap 1 lands, add type annotations to all macros.
5. **Third-party component packages**: Establish conventions for the ecosystem.
