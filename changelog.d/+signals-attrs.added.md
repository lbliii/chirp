✨ **`signal_attrs()` template global — bind a signal on an existing element.**
A third signal binding helper alongside `signal()` / `signal_block()`: it emits the
binding **attributes only** (`sse-swap="name" hx-target="this"`) for placement
inside an element you already have — `<section class="board" {{ signal_attrs('stats') }}>` —
so a layout's own CSS-grid / flex container (or a `<ul>`) becomes a live sink
without an injected `<span>`/`<div>` wrapper breaking its layout. Unlike a
hand-written `sse-swap` attribute, the `signal_attrs('x')` call is recorded for
topic scoping and recognised by the `signal_dead_binding` contract by its call-site,
so the binding is validated even though the `sse-swap` is produced at render time.
