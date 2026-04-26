"""Template, Fragment, Page, Stream, TemplateStream, and ValidationError return types.

Frozen dataclasses that handlers return. The content negotiation layer
inspects these to dispatch to the kida renderer.
"""

import warnings
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from chirp.pages.types import ContextProvider, LayoutChain
    from chirp.templating.composition import PageComposition

# Valid htmx swap strategies (base value before any modifiers like
# "innerHTML transition:true" or "outerHTML show:top").
type SwapStrategy = Literal[
    "innerHTML",
    "outerHTML",
    "textContent",
    "beforebegin",
    "afterbegin",
    "beforeend",
    "afterend",
    "delete",
    "none",
    "true",
]

_VALID_SWAP_STRATEGIES: frozenset[str] = frozenset(
    {
        "innerHTML",
        "outerHTML",
        "textContent",
        "beforebegin",
        "afterbegin",
        "beforeend",
        "afterend",
        "delete",
        "none",
        "true",
    }
)


def _validate_swap(value: str | None) -> None:
    """Validate htmx swap strategy, allowing modifiers after base value."""
    if value is None:
        return
    stripped = value.strip()
    if not stripped:
        raise ValueError("swap must not be empty or whitespace-only")
    base = stripped.split()[0]
    if base not in _VALID_SWAP_STRATEGIES:
        raise ValueError(
            f"Invalid swap strategy {base!r} (from {value!r}). "
            f"Valid strategies: {', '.join(sorted(_VALID_SWAP_STRATEGIES))}"
        )


@dataclass(frozen=True, slots=True)
class Template:
    """Render a full kida template.

    Usage::

        return Template("page.html", title="Home", items=items)
    """

    template_name: str
    context: dict[str, Any] = field(default_factory=dict)

    def __init__(self, template_name: str, /, **context: Any) -> None:
        object.__setattr__(self, "template_name", template_name)
        object.__setattr__(self, "context", context)

    @property
    def name(self) -> str:
        """Deprecated alias for ``template_name``."""
        warnings.warn(
            "Template.name is deprecated, use .template_name instead",
            DeprecationWarning,
            stacklevel=2,
        )
        return self.template_name

    @staticmethod
    def inline(source: str, /, **context: Any) -> InlineTemplate:
        """Create a template from a string.  For prototyping only.

        Usage::

            return Template.inline("<h1>{{ title }}</h1>", title="Hello")

        """
        return InlineTemplate(source, **context)


@dataclass(frozen=True, slots=True)
class InlineTemplate:
    """A template rendered from a string source.  For prototyping.

    Separate type so the content negotiation layer can distinguish it
    from file-based templates, and ``app.check()`` can warn about
    inline templates in production code.
    """

    source: str
    context: dict[str, Any] = field(default_factory=dict)

    def __init__(self, source: str, /, **context: Any) -> None:
        object.__setattr__(self, "source", source)
        object.__setattr__(self, "context", context)


@dataclass(frozen=True, slots=True)
class Fragment:
    """Render a named block from a kida template.

    The *target* field controls how the fragment is delivered:

    - **OOB responses**: *target* specifies the DOM element ID for the
      out-of-band swap.  If *target* is ``None`` (the default), the
      block name is used as the target ID.
    - **SSE streams**: *target* becomes the SSE event name.  Templates
      use ``sse-swap="{target}"`` to receive the fragment.  If *target*
      is ``None``, the event name defaults to ``"fragment"``.

    Usage::

        return Fragment("search.html", "results_list", results=results)

    With explicit OOB target::

        Fragment("cart.html", "counter", target="cart-counter", count=5)

    With explicit SSE event name::

        yield Fragment("dashboard.html", "stats_panel",
                       target="stats-update", stats=stats)
        # Client: <div sse-swap="stats-update">
    """

    template_name: str
    block_name: str
    target: str | None = None
    swap: str | None = None
    context: dict[str, Any] = field(default_factory=dict)

    def __init__(
        self,
        template_name: str,
        block_name: str,
        /,
        *,
        target: str | None = None,
        swap: str | None = None,
        **context: Any,
    ) -> None:
        _validate_swap(swap)
        object.__setattr__(self, "template_name", template_name)
        object.__setattr__(self, "block_name", block_name)
        object.__setattr__(self, "target", target)
        object.__setattr__(self, "swap", swap)
        object.__setattr__(self, "context", context)


@dataclass(frozen=True, slots=True)
class Page:
    """Render a full template or a request-aware page fragment.

    Combines Template and Fragment semantics.  The content negotiation
    layer inspects the incoming request headers and renders:

    * **Full template** for normal browser navigations and htmx
      history-restore requests.
    * **Named fragment block** for narrow htmx fragment requests
      (``HX-Request`` without ``HX-History-Restore-Request``).
    * **Page block** for boosted navigations when a page needs a wider,
      fragment-safe root than the narrow fragment block.

    This eliminates the manual ``if request.is_htmx`` boilerplate
    that every htmx-reachable route would otherwise need.

    Usage::

        return Page("hackernews.html", "story_list",
                     stories=stories, page="list")

    With an explicit page-level block for boosted navigation::

        return Page(
            "dashboard.html",
            "results_panel",
            page_block_name="page_root",
            stats=stats,
        )

    For page-directory/app-shell templates that follow Chirp's conventional
    ``page_root`` / ``page_content`` blocks::

        return Page.mounted("dashboard/page.html", stats=stats)
    """

    template_name: str
    block_name: str
    page_block_name: str | None = None
    context: dict[str, Any] = field(default_factory=dict)

    def __init__(
        self,
        template_name: str,
        block_name: str | None = None,
        /,
        *,
        page_block_name: str | None = None,
        **context: Any,
    ) -> None:
        if block_name is None:
            raise TypeError(
                'Page requires a block name: Page("page.html", "content_block").\n'
                "For a plain full-page render without htmx negotiation, "
                'use Template("page.html", **ctx).\n'
                "See the return-values docs for the decision tree: "
                "docs/core-concepts/return-values.md"
            )
        object.__setattr__(self, "template_name", template_name)
        object.__setattr__(self, "block_name", block_name)
        object.__setattr__(self, "page_block_name", page_block_name)
        object.__setattr__(self, "context", context)

    @property
    def name(self) -> str:
        """Deprecated alias for ``template_name``."""
        warnings.warn(
            "Page.name is deprecated, use .template_name instead",
            DeprecationWarning,
            stacklevel=2,
        )
        return self.template_name

    @property
    def effective_page_block_name(self) -> str:
        """Block used when a full page fragment root is required."""
        return self.page_block_name or self.block_name

    @staticmethod
    def mounted(
        template_name: str,
        /,
        *,
        block_name: str = "page_content",
        page_block_name: str = "page_root",
        **context: Any,
    ) -> Page:
        """Create a Page for mounted page-directory/app-shell templates."""
        return Page(
            template_name,
            block_name,
            page_block_name=page_block_name,
            **context,
        )


@dataclass(frozen=True, slots=True)
class Action:
    """Represent a side-effect endpoint that should not swap response HTML.

    Defaults to ``204 No Content`` so htmx receives a successful response
    without replacing any target content. Optional htmx response headers can
    be attached for client-side behavior.

    Usage::

        return Action()
        return Action(trigger="saved")
        return Action(refresh=True)
    """

    status: int = 204
    trigger: str | dict[str, Any] | None = None
    refresh: bool = False


class MutationResult:
    """Mutation success with progressive enhancement.

    Also exported as ``FormAction`` — both names resolve to the same class.
    Use ``FormAction`` when the mutation is a form submission and
    ``MutationResult`` for non-form mutations (API endpoints, htmx-driven
    actions); the behavior is identical.

    Auto-negotiates htmx vs non-htmx responses for any mutation
    (POST, PUT, PATCH, DELETE):

    - **htmx + fragments**: renders fragments (OOB-style) + optional
      ``HX-Trigger`` header.  No redirect.
    - **htmx + no fragments**: ``HX-Redirect`` to ``redirect`` URL
      (client-side full redirect).
    - **non-htmx**: 303 redirect to ``redirect`` URL.

    Usage (form submission)::

        return MutationResult("/contacts")

    With fragments for htmx (non-htmx still gets a redirect)::

        return MutationResult(
            "/contacts",
            Fragment("contacts.html", "table", contacts=contacts),
            Fragment("contacts.html", "count", target="count", count=len(contacts)),
            trigger="contactAdded",
        )

    DELETE with confirmation::

        return MutationResult(
            "/items",
            Fragment("items.html", "list", items=remaining),
            trigger="itemDeleted",
        )
    """

    __slots__ = ("fragments", "redirect", "status", "trigger")

    def __init__(
        self,
        redirect: str,
        *fragments: Fragment,
        trigger: str | None = None,
        status: int = 303,
    ) -> None:
        self.redirect = redirect
        self.fragments = fragments
        self.trigger = trigger
        self.status = status


FormAction = MutationResult
"""Form-submission alias of :class:`MutationResult`. Same class, different name."""


@dataclass(frozen=True, slots=True)
class ValidationError:
    """Return a form fragment with 422 status for htmx validation.

    Bundles the most common htmx form pattern: validate server-side,
    re-render the form fragment with errors on failure, return 422 so
    htmx knows to swap the error content.

    The negotiation layer renders this as a ``Fragment`` with status
    422.  If *retarget* is set, the ``HX-Retarget`` response header is
    added so htmx swaps errors into a different element than the
    original trigger.

    Usage::

        result = validate(form, rules)
        if not result:
            return ValidationError("form.html", "form_body",
                                   errors=result.errors, form=form)

    With retarget::

        return ValidationError("form.html", "form_errors",
                               retarget="#error-banner",
                               errors=result.errors)
    """

    template_name: str
    block_name: str
    retarget: str | None = None
    context: dict[str, Any] = field(default_factory=dict)

    def __init__(
        self,
        template_name: str,
        block_name: str,
        /,
        *,
        retarget: str | None = None,
        **context: Any,
    ) -> None:
        object.__setattr__(self, "template_name", template_name)
        object.__setattr__(self, "block_name", block_name)
        object.__setattr__(self, "retarget", retarget)
        object.__setattr__(self, "context", context)


@dataclass(frozen=True, slots=True)
class Stream:
    """Render a kida template with progressive streaming.

    **When to use:** All data is known upfront (or resolves quickly), but
    the template is large and you want the browser to start painting before
    the full HTML is ready.  Context awaitables resolve concurrently before
    streaming begins.

    **Not this — use TemplateStream** when the template itself consumes an
    async iterator (``{% async for %}``, ``{{ await }}``).

    **Not this — use Suspense** when you want a shell/skeleton rendered
    immediately while slow data loads in the background.

    Usage::

        return Stream("dashboard.html",
            header=site_header(),
            stats=await load_stats(),
            feed=await load_feed(),
        )
    """

    template_name: str
    context: dict[str, Any] = field(default_factory=dict)

    def __init__(self, template_name: str, /, **context: Any) -> None:
        object.__setattr__(self, "template_name", template_name)
        object.__setattr__(self, "context", context)


@dataclass(frozen=True, slots=True)
class TemplateStream:
    """Render a template with Kida's render_stream_async.

    **When to use:** The template itself consumes an async iterator via
    ``{% async for %}`` or ``{{ await }}``.  HTML chunks stream to the
    browser as the iterator yields.  O(n) — one pass, not re-render per
    item.  Ideal for LLM token streaming and long async feeds.

    **Not this — use Stream** when all data resolves upfront and you just
    want chunked transfer of a large template.

    **Not this — use Suspense** when you want a shell rendered first, then
    slow sections filled in as out-of-band swaps.

    Usage::

        return TemplateStream("chat.html",
            stream=llm.stream(prompt),
            prompt=prompt,
        )
    """

    template_name: str
    context: dict[str, Any] = field(default_factory=dict)

    def __init__(self, template_name: str, /, **context: Any) -> None:
        object.__setattr__(self, "template_name", template_name)
        object.__setattr__(self, "context", context)


@dataclass(frozen=True, slots=True)
class Suspense:
    """Render a page shell immediately, then fill in deferred blocks via OOB.

    **When to use:** The page has slow data sources (DB queries, API calls)
    and you want the user to see the page shell/skeleton instantly.  Deferred
    blocks stream in as out-of-band swaps when their data resolves.  Best
    for dashboards, detail pages with multiple independent data sources.

    **Not this — use Stream** when all data resolves quickly and you just
    want chunked transfer of a large template.

    **Not this — use TemplateStream** when the template consumes an async
    iterator inline (``{% async for %}``).

    Like React's ``<Suspense>`` but server-rendered.  Context values that
    are awaitables are **deferred**: the shell renders with those keys
    set to the ``DEFERRED`` sentinel (showing skeleton/fallback content),
    then each block is re-rendered with real data and streamed as an OOB
    swap chunk.

    The shell also sets ``__chirp_defer_pending__`` (see
    ``CHIRP_DEFER_PENDING_KEY`` in ``chirp.templating.suspense``) to a
    ``frozenset`` of deferred context key names; deferred block re-renders
    use an empty frozenset.  Do not use that name for your own context keys.

    **Templates:** Use ``{% if stats is deferred %}`` for skeleton vs loaded.
    Bare ``{% if stats %}`` raises ``TypeError`` to prevent the common
    footgun where empty results (``[]``, ``0``, ``""``) keep skeletons
    visible after resolution.

    For htmx navigations, blocks arrive as ``hx-swap-oob`` elements.
    For initial page loads, ``<template>`` + inline ``<script>`` pairs
    handle the swap without any framework.

    Usage::

        return Suspense("dashboard.html",
            header=site_header(),          # sync — in the shell
            stats=load_stats(),            # awaitable — deferred
            feed=load_feed(),              # awaitable — deferred
        )

    Template (skeleton vs loaded — use ``is deferred``, not ``{% if stats %}``)::

        {% block stats %}
          {% if stats is deferred %}
            <div class="skeleton">Loading stats...</div>
          {% else %}
            {% for s in stats %}...{% end %}
          {% end %}
        {% end %}

    Block-to-DOM mapping defaults to block name = element ID.
    Override with *defer_map*::

        Suspense("page.html", defer_map={"stats": "stats-panel"}, ...)

    When static analysis misses blocks (e.g. deferred values passed
    through macro calls), list them explicitly with *defer_blocks*::

        Suspense("page.html",
            defer_blocks=("hero_stars", "footer_stars"),
            stars=fetch_stars(),
        )

    If a deferred value fails after the shell is sent, the skeleton is
    replaced with an error indicator.  Use *error_block* to render a
    custom fallback from the global ``suspense_error_template``
    (configured via ``AppConfig``).  When omitted, the ``error_block``
    from ``AppConfig.suspense_error_block`` is used.  If no error
    template is configured, a hardcoded default is used::

        Suspense("page.html",
            error_block="custom_fallback",
            stats=load_stats(),
        )
    """

    template_name: str
    context: dict[str, Any] = field(default_factory=dict)
    defer_map: dict[str, str] = field(default_factory=dict)
    defer_blocks: tuple[str, ...] | None = None
    error_block: str | None = None

    def __init__(
        self,
        template_name: str,
        /,
        *,
        defer_map: dict[str, str] | None = None,
        defer_blocks: tuple[str, ...] | None = None,
        error_block: str | None = None,
        **context: Any,
    ) -> None:
        object.__setattr__(self, "template_name", template_name)
        object.__setattr__(self, "context", context)
        object.__setattr__(self, "defer_map", defer_map or {})
        object.__setattr__(self, "defer_blocks", defer_blocks)
        object.__setattr__(self, "error_block", error_block)


@dataclass(frozen=True, slots=True)
class LayoutSuspense:
    """Suspense with layout chain — used when Suspense is returned from mount_pages.

    Carries layout metadata so the first chunk is wrapped in the layout shell
    (head, CSS, sidebar, etc.). OOB chunks target block IDs inside the page.
    """

    suspense: Suspense
    layout_chain: Any  # LayoutChain, but Any to avoid circular import
    context: dict[str, Any] = field(default_factory=dict)
    request: Any = None

    def __init__(
        self,
        suspense: Suspense,
        layout_chain: Any,
        /,
        *,
        context: dict[str, Any] | None = None,
        request: Any = None,
    ) -> None:
        object.__setattr__(self, "suspense", suspense)
        object.__setattr__(self, "layout_chain", layout_chain)
        object.__setattr__(self, "context", context or {})
        object.__setattr__(self, "request", request)


@dataclass(frozen=True, slots=True)
class LayoutPage:
    """Render a page within a filesystem-based layout chain.

    Used by ``mount_pages()`` routes.  The negotiation layer composes
    the layout chain at the correct depth based on ``HX-Target``:

    * **Full page load**: render all layouts nested around the page block
    * **Boosted navigation**: render from the targeted layout down using
      the page block
    * **Fragment request**: render just the fragment block

    The *layout_chain* and *context_providers* are set by the pages
    discovery system — handlers never construct this directly.

    Usage (internal — set by the pages framework)::

        return LayoutPage(
            "page.html",
            "content",
            page_block_name="page_root",
            layout_chain=chain,
            context_providers=providers,
            title="Home",
        )
    """

    template_name: str
    block_name: str
    page_block_name: str | None = None
    layout_chain: LayoutChain | None = None
    context_providers: tuple[ContextProvider, ...] = ()
    context: dict[str, Any] = field(default_factory=dict)

    def __init__(
        self,
        template_name: str,
        block_name: str,
        /,
        *,
        page_block_name: str | None = None,
        layout_chain: LayoutChain | None = None,
        context_providers: tuple[ContextProvider, ...] = (),
        **context: Any,
    ) -> None:
        object.__setattr__(self, "template_name", template_name)
        object.__setattr__(self, "block_name", block_name)
        object.__setattr__(self, "page_block_name", page_block_name)
        object.__setattr__(self, "layout_chain", layout_chain)
        object.__setattr__(self, "context_providers", context_providers)
        object.__setattr__(self, "context", context)

    @property
    def name(self) -> str:
        """Deprecated alias for ``template_name``."""
        warnings.warn(
            "LayoutPage.name is deprecated, use .template_name instead",
            DeprecationWarning,
            stacklevel=2,
        )
        return self.template_name

    @property
    def effective_page_block_name(self) -> str:
        """Block used when layouts or boosted swaps need the page root."""
        return self.page_block_name or self.block_name


@dataclass(frozen=True, slots=True)
class OOB:
    """Compose a primary response with out-of-band fragment swaps.

    htmx processes the first element as the normal swap target, then
    scans for elements with ``hx-swap-oob`` and swaps them into the
    page by ID.  ``OOB`` renders all fragments into a single HTML
    response with the correct attributes.

    Each OOB fragment's target ID defaults to its ``block_name``
    (convention), but can be overridden via ``Fragment(..., target="id")``.

    Usage::

        return OOB(
            Fragment("products.html", "list", products=products),
            Fragment("cart.html", "counter", count=new_count),
            Fragment("notifications.html", "badge", unread=3),
        )

    The first fragment is the primary swap target.  All subsequent
    fragments are rendered with ``hx-swap-oob="true"`` and an ``id``
    matching their target.
    """

    main: Fragment | Template | Page | LayoutPage | PageComposition
    oob_fragments: tuple[Fragment, ...]

    def __init__(
        self,
        main: Fragment | Template | Page | LayoutPage | PageComposition,
        /,
        *oob_fragments: Fragment,
    ) -> None:
        # Fail fast: streaming types cannot be OOB main — they need buffered
        # responses to append fragments. Check here rather than at render time.
        from chirp.realtime.events import EventStream

        _streaming = (Suspense, Stream, TemplateStream, EventStream)
        if isinstance(main, _streaming):
            raise TypeError(
                f"OOB main cannot be {type(main).__name__} "
                "(a streaming response type). "
                "OOB requires a buffered response to append fragments. "
                "Buffered return types: Template, Fragment, Page, "
                "MutationResult/FormAction, ValidationError. Streaming types "
                "(Stream, Suspense, EventStream) cannot carry OOB siblings — "
                "yield additional Fragment values from inside the stream instead."
            )
        object.__setattr__(self, "main", main)
        object.__setattr__(self, "oob_fragments", oob_fragments)
