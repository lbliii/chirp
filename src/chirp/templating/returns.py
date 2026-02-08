"""Template, Fragment, Page, Stream, and ValidationError return types.

Frozen dataclasses that handlers return. The content negotiation layer
inspects these to dispatch to the kida renderer.
"""

from dataclasses import dataclass, field
from typing import Any


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


@dataclass(frozen=True, slots=True)
class Fragment:
    """Render a named block from a kida template.

    When used inside an ``OOB`` response, *target* specifies the DOM
    element ID for the out-of-band swap.  If *target* is ``None``
    (the default), the block name is used as the target ID.

    Usage::

        return Fragment("search.html", "results_list", results=results)

    With explicit OOB target::

        Fragment("cart.html", "counter", target="cart-counter", count=5)
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
