"""Page-level htmx provisioning contract.

htmx attributes (``hx-get``, ``hx-post``, ``sse-connect``, ...) are inert
without the htmx runtime loaded on the page. A template that emits ``hx-*`` /
``sse-*`` but ships no htmx ``<script>`` and does not opt into Chirp's htmx
injection renders a UI whose buttons/forms/streams silently do nothing — the
markup looks correct, the network never fires, and there is no console error to
point at the cause.

Chirp provisions htmx two ways, and this rule recognizes **both**:

- **Mode A — ``AppConfig(htmx=True)``** (#184): Chirp's ``HtmxInject``
  middleware appends the htmx runtime to *every* full-page response. This is an
  app-global guarantee, so when the flag is set every page is provisioned
  regardless of templates and the rule returns no offenders.
- **Mode B — an explicit htmx ``<script src="...htmx...">``** reachable from the
  page **through its own composition chain**: its own template, a template it
  ``{% extends %}`` / ``{% include %}``, or — for filesystem-routing pages — a
  ``_layout.html`` in the layout chain (and that layout's own extends/include
  closure, e.g. the framework shell ``chirp/layouts/shell.html`` chirp-ui apps
  extend). Because htmx loads page-wide, a single matching script anywhere in
  *that page's* reachable closure provisions the whole composed page.

**Per-offender, per-composing-chain — not app-global, not layout-union (the
#185 false-negative fix).** Mode B is evaluated *per offending template* against
**its own** reachable closure, never the union of every template in the app.
That closure is seeded from the offender itself **plus only the layouts that
actually compose THAT page** — its own ``_layout.html`` ancestry — not the union
of every layout the app discovered. An htmx script that sits only in an
unrelated sibling page's standalone template, *or in a layout that composes a
different section*, does **not** provision a page that never reaches it.

Concretely, two false negatives are closed here:

- **Page-leaf union (closed earlier).** If page A (a standalone template) ships
  its own htmx ``<script>`` and uses ``hx-*``, page A passes — but sibling page
  B that uses ``hx-*`` with no script in *B's* own closure still ERRORs.
- **Layout union (closed here).** If section A uses a layout that ships an htmx
  ``<script>`` and section B uses a *different*, script-less layout, B still
  ERRORs. A prior union over all discovered layouts wrongly cleared B because
  A's layout script appeared in the global layout seed; that is a fail-loud
  false negative.

The closure for an offender is seeded from: the offender itself, plus the
layouts of **its own** composing chain(s) — looked up by leaf-template name via
*layout_chains_by_leaf*. A filesystem page is seeded with its own
``_layout.html`` ancestry; a decorator-route / standalone ``Template`` offender
with no layout chain self-provisions (its seed is just itself). The seed set is
then expanded transitively over ``extends`` / ``include`` / ``import``
references. It is *not* seeded from other offenders, other page leaves, or
layouts that compose other pages.

Reachability matters: Chirp's loader lists *every* bundled framework template
(``chirp/layouts/shell.html`` ships an htmx script) even for apps that never use
the shell. A naive "is an htmx script present anywhere in the loader catalog"
gate would therefore never fire. This rule instead scans only the closure of
templates the offender actually composes.

Only when **neither** mode is present does an app template that uses ``hx-*`` /
``sse-*`` emit an ERROR (category ``htmx_provisioning``). The usage scan skips
framework-shipped (``chirp/`` / ``chirpui/`` / ``chirp_docs/``) templates —
provisioning those is not the app developer's responsibility.

If you self-host htmx under a filename the ``src``-contains-``htmx`` heuristic
cannot see (a custom bundle, ``/static/vendor.js``, an npm import), set
``AppConfig(htmx=True)`` as the explicit opt-in so this check passes.
"""

import re
from collections.abc import Iterable, Mapping

from .template_scan import extract_template_references, resolve_template_reference
from .types import ContractIssue, Severity

# Attribute names that imply a client-side htmx request or listener and so
# require the htmx runtime. Scoped to unambiguous usage signals: the hx-VERB
# attributes, hx-trigger/hx-boost/hx-ext, and the SSE-extension attributes.
# Deliberately excludes bare hx-target / hx-swap / hx-swap-oob / hx-disinherit,
# which appear as inherited / OOB metadata in framework output and deferred
# fragments and are not standalone provisioning triggers.
_HTMX_USAGE = re.compile(
    r"\b(?:hx-(?:get|post|put|patch|delete|trigger|boost|ext)|sse-connect|sse-swap)\s*=",
    re.IGNORECASE,
)

# An htmx <script src="..."> reachable from the page. Matches any src URL
# containing 'htmx' so unpkg.com/htmx.org@2.0.4, htmx-ext-sse@2.2.2/sse.js, the
# jsdelivr variants, and a self-hosted /static/htmx.min.js all count.
_HTMX_SCRIPT = re.compile(
    r"""<script\b[^>]*\bsrc\s*=\s*["'][^"']*htmx[^"']*["']""",
    re.IGNORECASE,
)

# Framework-shipped template namespaces. Their hx-* usage is not the app
# developer's responsibility (the developer cannot edit them) and the host app
# is responsible for page-wide htmx provisioning. Mirrors the chirp/ + chirpui/
# skip used across the checker, plus chirp_docs/ (the DocsPlugin namespace whose
# partials emit hx-get search/nav but ship no script — the host page provisions
# htmx). The provisioning scan deliberately does NOT skip these.
_FRAMEWORK_NS = ("chirp/", "chirpui/", "chirp_docs/")


def _reachable_closure(
    seeds: Iterable[str],
    template_sources: dict[str, str],
    template_aliases: Mapping[str, str] | None,
) -> set[str]:
    """Transitive ``extends`` / ``include`` closure of ``seeds``.

    Walks Kida cross-template references so the provisioning scan only sees
    templates the app actually composes (not the entire bundled framework
    catalog). Missing references are simply skipped.
    """
    closure: set[str] = set()
    stack = [name for name in seeds if name]
    while stack:
        name = stack.pop()
        if name in closure:
            continue
        closure.add(name)
        source = template_sources.get(name)
        if source is None:
            continue
        for ref in extract_template_references(source):
            resolved = resolve_template_reference(ref, name, template_aliases)
            if resolved not in closure:
                stack.append(resolved)
    return closure


def _closure_has_htmx_script(closure: Iterable[str], template_sources: dict[str, str]) -> bool:
    """True if any template in *closure* ships an htmx ``<script src=...>``."""
    for name in closure:
        source = template_sources.get(name)
        if source is not None and _HTMX_SCRIPT.search(source):
            return True
    return False


def _layout_names(chain_or_chains: object) -> set[str]:
    """Template names of every layout in *chain_or_chains*.

    Accepts a single ``LayoutChain`` (anything with a ``.layouts`` attribute) or
    an iterable of chains. The iterable form lets a single leaf template that is
    composed by more than one chain (e.g. the same ``page.html`` mounted at two
    paths) be seeded with the *union* of every composing layout. Returns an empty
    set for a value that is neither a chain nor an iterable of chains.
    """
    if hasattr(chain_or_chains, "layouts"):
        chains: Iterable[object] = (chain_or_chains,)
    elif isinstance(chain_or_chains, (list, tuple, set, frozenset)):
        chains = chain_or_chains
    else:
        chains = ()
    names: set[str] = set()
    for chain in chains:
        for layout in getattr(chain, "layouts", ()):
            layout_name = getattr(layout, "template_name", None)
            if layout_name:
                names.add(layout_name)
    return names


def check_htmx_provisioning(
    template_sources: dict[str, str],
    config: object,
    *,
    layout_chains: Iterable[object] = (),
    layout_chains_by_leaf: Mapping[str, object] | None = None,
    page_leaf_templates: Iterable[str] = (),
    full_page_templates: Iterable[str] | None = None,
    template_aliases: Mapping[str, str] | None = None,
) -> list[ContractIssue]:
    """Flag app templates that use ``hx-*`` / ``sse-*`` without htmx provisioned.

    Two provisioning modes (see the module docstring):

    - **Mode A** — ``AppConfig(htmx=True)`` provisions the whole app globally;
      the rule returns no offenders.
    - **Mode B** — evaluated **per page, per composing chain**. Only *full-page*
      renders (templates returned via ``Template`` / ``Page`` / ``Suspense`` /
      ``Stream`` or a filesystem page leaf — see *full_page_templates*) are
      checked: each must ship an htmx ``<script>`` somewhere in *its own*
      composition closure (its own ``extends`` / ``include`` / macro-import
      references plus the layouts of **its own** ``_layout.html`` chain). An
      htmx script in an unrelated sibling page — or in a layout that composes a
      *different* page — never suppresses this page (#185).

    *layout_chains_by_leaf* maps a leaf-template name to the
    :class:`~chirp.pages.types.LayoutChain` that composes it; when provided,
    each leaf is seeded with **only** that chain's layouts (precise per-page
    semantics). When it is ``None`` (older callers / focused unit tests with no
    per-leaf route information) the rule falls back to the flat *layout_chains*
    union — every offender is seeded with every layout — which is only sound for
    single-chain apps. The real checker always supplies
    *layout_chains_by_leaf*, so production never unions layouts across sections.

    Fragment-only templates (returned solely via ``Fragment`` /
    ``ValidationError`` / ``OOB``) are **not** flagged on their own: they swap
    into an already-loaded host page, so the host page owns htmx provisioning —
    exactly like framework-shipped partials. When *full_page_templates* is
    ``None`` (callers that have no route information, e.g. focused unit tests)
    every offender is treated as a full-page render so the check stays strict.
    """
    # Offending = non-framework templates that actually use htmx attributes.
    offenders: list[str] = []
    for template_name, source in template_sources.items():
        if template_name.startswith(_FRAMEWORK_NS):
            continue
        if _HTMX_USAGE.search(source):
            offenders.append(template_name)
    if not offenders:
        return []

    # Mode A: AppConfig(htmx=True) provisions every full-page response app-wide.
    # getattr default keeps the rule forward-compatible if the flag is ever
    # absent on an older config.
    if getattr(config, "htmx", False):
        return []

    # Per-leaf layout seeds: each leaf template is seeded with ONLY the layouts
    # of its own composing chain(s), looked up by leaf-template name. A layout
    # that composes a different section never appears here, so it cannot
    # suppress this page (the #185 layout-level false negative).
    if layout_chains_by_leaf is not None:
        leaf_layout_seeds: dict[str, set[str]] = {}
        for leaf_name, chain in layout_chains_by_leaf.items():
            if leaf_name:
                leaf_layout_seeds.setdefault(leaf_name, set()).update(_layout_names(chain))
        # No global fallback union: an offender with no chain self-provisions
        # (its seed is just itself, expanded over its own extends/include/import).
        fallback_layout_seeds: set[str] = set()
    else:
        # Legacy path: no per-leaf route info supplied. Fall back to the flat
        # layout_chains union (sound only for single-chain apps; the real
        # checker always passes layout_chains_by_leaf so this is not hit there).
        leaf_layout_seeds = {}
        fallback_layout_seeds = set()
        for chain in layout_chains:
            fallback_layout_seeds.update(_layout_names(chain))

    # Which offenders are full pages? Only full pages must self-provision. A
    # fragment-only template swaps into its host page and is the host's concern.
    if full_page_templates is None:
        # No route info — stay strict: treat every offender as a full page.
        full_pages = set(offenders)
    else:
        full_pages = set(full_page_templates)
        full_pages.update(name for name in page_leaf_templates if name)

    issues: list[ContractIssue] = []
    for template_name in offenders:
        if template_name not in full_pages:
            # Fragment-only: swapped into an already-provisioned host page.
            continue
        # Per-page closure: the page itself + the layouts of ITS OWN composing
        # chain, expanded over extends/include/import. A sibling page's
        # standalone script, or a layout composing a different page, is not in
        # this set, so it cannot suppress this page (#185).
        page_layouts = leaf_layout_seeds.get(template_name, fallback_layout_seeds)
        seeds: set[str] = {template_name, *page_layouts}
        reachable = _reachable_closure(seeds, template_sources, template_aliases)
        if _closure_has_htmx_script(reachable, template_sources):
            continue
        issues.append(
            ContractIssue(
                severity=Severity.ERROR,
                category="htmx_provisioning",
                message=(
                    f"Template '{template_name}' uses htmx attributes "
                    "(hx-*/sse-*) but htmx is not provisioned — those "
                    "attributes are inert and the UI silently does nothing. "
                    "Provision htmx by setting AppConfig(htmx=True) or adding "
                    'an htmx <script src="...htmx..."> to the layout/extends '
                    "chain."
                ),
                template=template_name,
            )
        )
    return issues
