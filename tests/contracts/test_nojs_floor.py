"""No-JS progressive-enhancement floor contract (#152)."""

from chirp.contracts.rules_nojs_floor import check_nojs_mutation_fallback
from chirp.templating.returns import Fragment, MutationResult


class _Route:
    def __init__(self, path, methods, handler, *, referenced=False) -> None:
        self.path = path
        self.methods = set(methods)
        self.handler = handler
        self.referenced = referenced


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
