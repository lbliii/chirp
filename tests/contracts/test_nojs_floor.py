"""No-JS progressive-enhancement floor contract (#152)."""

from chirp.contracts.rules_nojs_floor import check_nojs_mutation_fallback
from chirp.templating.returns import Fragment, MutationResult


class _Route:
    def __init__(
        self, path, methods, handler, *, referenced=False, page_source_handler=None
    ) -> None:
        self.path = path
        self.methods = set(methods)
        self.handler = handler
        self.referenced = referenced
        if page_source_handler is not None:
            self.page_source_handler = page_source_handler


class _Router:
    def __init__(self, routes) -> None:
        self.routes = routes


def _categories(router) -> list[str]:
    return [i.category for i in check_nojs_mutation_fallback(router)]


def test_htmx_only_mutation_flagged_as_info() -> None:
    def save(request):
        return Fragment("page.html", "row")

    router = _Router([_Route("/save", ["POST"], save)])
    issues = check_nojs_mutation_fallback(router)
    assert [i.category for i in issues] == ["nojs_floor"]
    # INFO by default: htmx-only mutation is a legitimate design choice;
    # apps enforce the floor by promoting the category via override.
    assert issues[0].severity.name == "INFO"


def test_formaction_fallback_suppresses_warning() -> None:
    def save(request):
        if request.is_htmx:
            return Fragment("page.html", "row")
        return MutationResult("/done")

    router = _Router([_Route("/save", ["POST"], save)])
    assert _categories(router) == []


def test_referenced_route_excluded() -> None:
    def stream(request):
        return Fragment("page.html", "row")

    router = _Router([_Route("/save", ["POST"], stream, referenced=True)])
    assert _categories(router) == []


def test_get_route_not_flagged() -> None:
    def show(request):
        return Fragment("page.html", "row")

    router = _Router([_Route("/show", ["GET"], show)])
    assert _categories(router) == []


def test_full_page_return_not_flagged() -> None:
    def save(request):
        from chirp.templating.returns import Page

        return Page("page.html", "row")

    router = _Router([_Route("/save", ["POST"], save)])
    assert _categories(router) == []


def test_scans_page_source_handler_for_mounted_routes() -> None:
    """For mounted-page routes the real source is route.page_source_handler.

    route.handler is an async wrapper containing no return statements; scanning
    it would miss the htmx-only return (false negative). The rule must scan
    page_source_handler.
    """

    async def _page_wrapper(request):  # the async wrapper registered as handler
        return await request

    def real_page_handler(request):  # the user's real handler
        return Fragment("page.html", "row")

    router = _Router(
        [_Route("/save", ["POST"], _page_wrapper, page_source_handler=real_page_handler)]
    )
    assert _categories(router) == ["nojs_floor"]


def test_page_source_handler_fallback_suppresses() -> None:
    async def _page_wrapper(request):
        return await request

    def real_page_handler(request):
        if request.is_htmx:
            return Fragment("page.html", "row")
        return MutationResult("/done")

    router = _Router(
        [_Route("/save", ["POST"], _page_wrapper, page_source_handler=real_page_handler)]
    )
    assert _categories(router) == []
