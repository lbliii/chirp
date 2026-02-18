"""Template, Fragment, Page, Stream, and ValidationError return types.

Frozen dataclasses that handlers return. The content negotiation layer
inspects these to dispatch to the kida renderer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from chirp.pages.types import ContextProvider, LayoutChain


@dataclass(frozen=True, slots=True)
class Template:
    """Render a full kida template.

    Usage::

        return Template("page.html", title="Home", items=items)
    """

    name: str
    context: dict[str, Any] = field(default_factory=dict)

    def __init__(self, name: str, /, **context: Any) -> None:
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "context", context)

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
    context: dict[str, Any] = field(default_factory=dict)

    def __init__(
        self,
        template_name: str,
        block_name: str,
        /,
        *,
        target: str | None = None,
        **context: Any,
    ) -> None:
        object.__setattr__(self, "template_name", template_name)
        object.__setattr__(self, "block_name", block_name)
        object.__setattr__(self, "target", target)
        object.__setattr__(self, "context", context)


@dataclass(frozen=True, slots=True)
class Page:
    """Render a full template or a named block, depending on the request.

    Combines Template and Fragment semantics.  The content negotiation
    layer inspects the incoming request headers and renders:

    * **Full template** for normal browser navigations and htmx
      history-restore requests.
    * **Named block only** for htmx fragment requests (``HX-Request``
      without ``HX-History-Restore-Request``).

    This eliminates the manual ``if request.is_fragment`` boilerplate
    that every htmx-reachable route would otherwise need.

    Usage::

        return Page("hackernews.html", "story_list",
                     stories=stories, page="list")
    """

    name: str
    block_name: str
    context: dict[str, Any] = field(default_factory=dict)

    def __init__(self, name: str, block_name: str, /, **context: Any) -> None:
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "block_name", block_name)
        object.__setattr__(self, "context", context)


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


class FormAction:
    """Form success result with progressive enhancement.

    Auto-negotiates htmx vs non-htmx responses:

    - **htmx + fragments**: renders fragments (OOB-style) + optional
      ``HX-Trigger`` header.  No redirect.
    - **htmx + no fragments**: ``HX-Redirect`` to ``redirect`` URL
      (client-side full redirect).
    - **non-htmx**: 303 redirect to ``redirect`` URL.

    Usage::

        return FormAction("/contacts")

    With fragments for htmx (non-htmx still gets a redirect)::

        return FormAction(
            "/contacts",
            Fragment("contacts.html", "table", contacts=contacts),
            Fragment("contacts.html", "count", target="count", count=len(contacts)),
            trigger="contactAdded",
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

    Context values that are awaitables resolve concurrently.
    Each template section streams to the browser as its data arrives.

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
class Suspense:
    """Render a page shell immediately, then fill in deferred blocks via OOB.

    Like React's ``<Suspense>`` but server-rendered.  Context values that
    are awaitables are **deferred**: the shell renders with those keys
    set to ``None`` (showing skeleton/fallback content), then each block
    is re-rendered with real data and streamed as an OOB swap chunk.

    For htmx navigations, blocks arrive as ``hx-swap-oob`` elements.
    For initial page loads, ``<template>`` + inline ``<script>`` pairs
    handle the swap without any framework.

    Usage::

        return Suspense("dashboard.html",
            header=site_header(),          # sync — in the shell
            stats=load_stats(),            # awaitable — deferred
            feed=load_feed(),              # awaitable — deferred
        )

    Template (uses normal conditional rendering for skeletons)::

        {% block stats %}
          {% if stats %}
            {% for s in stats %}...{% end %}
          {% else %}
            <div class="skeleton">Loading stats...</div>
          {% end %}
        {% end %}

    Block-to-DOM mapping defaults to block name = element ID.
    Override with *defer_map*::

        Suspense("page.html", defer_map={"stats": "stats-panel"}, ...)
    """

    template_name: str
    context: dict[str, Any] = field(default_factory=dict)
    defer_map: dict[str, str] = field(default_factory=dict)

    def __init__(
        self,
        template_name: str,
        /,
        *,
        defer_map: dict[str, str] | None = None,
        **context: Any,
    ) -> None:
        object.__setattr__(self, "template_name", template_name)
        object.__setattr__(self, "context", context)
        object.__setattr__(self, "defer_map", defer_map or {})


@dataclass(frozen=True, slots=True)
class LayoutPage:
    """Render a page within a filesystem-based layout chain.

    Used by ``mount_pages()`` routes.  The negotiation layer composes
    the layout chain at the correct depth based on ``HX-Target``:

    * **Full page load**: render all layouts nested
    * **Boosted navigation**: render from the targeted layout down
    * **Fragment request**: render just the named block

    The *layout_chain* and *context_providers* are set by the pages
    discovery system — handlers never construct this directly.

    Usage (internal — set by the pages framework)::

        return LayoutPage(
            "page.html", "content",
            layout_chain=chain,
            context_providers=providers,
            title="Home",
        )
    """

    name: str
    block_name: str
    layout_chain: LayoutChain | None = None
    context_providers: tuple[ContextProvider, ...] = ()
    context: dict[str, Any] = field(default_factory=dict)

    def __init__(
        self,
        name: str,
        block_name: str,
        /,
        *,
        layout_chain: LayoutChain | None = None,
        context_providers: tuple[ContextProvider, ...] = (),
        **context: Any,
    ) -> None:
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "block_name", block_name)
        object.__setattr__(self, "layout_chain", layout_chain)
        object.__setattr__(self, "context_providers", context_providers)
        object.__setattr__(self, "context", context)


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

    main: Fragment | Template | Page
    oob_fragments: tuple[Fragment, ...]

    def __init__(
        self,
        main: Fragment | Template | Page,
        /,
        *oob_fragments: Fragment,
    ) -> None:
        object.__setattr__(self, "main", main)
        object.__setattr__(self, "oob_fragments", oob_fragments)
