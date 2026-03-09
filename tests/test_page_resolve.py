"""Tests for chirp.pages.resolve — page handler argument resolution."""

from dataclasses import dataclass

import pytest

from chirp.http.request import Request
from chirp.pages.resolve import resolve_kwargs, upgrade_result
from chirp.pages.shell_actions import ShellAction, ShellActions, ShellActionZone
from chirp.pages.types import ContextProvider, LayoutChain, LayoutInfo
from chirp.templating.composition import PageComposition
from chirp.templating.returns import OOB, LayoutPage, Page

# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


def _make_scope(**overrides: object) -> dict[str, object]:
    """Build a minimal valid ASGI HTTP scope."""
    base: dict[str, object] = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "path": "/",
        "raw_path": b"/",
        "query_string": b"",
        "root_path": "",
        "headers": [],
        "server": ("localhost", 8000),
        "client": ("127.0.0.1", 54321),
    }
    base.update(overrides)
    return base


def _make_receive(*bodies: bytes):
    """Create an ASGI receive callable that yields bodies."""
    messages = []
    for i, body in enumerate(bodies):
        is_last = i == len(bodies) - 1
        messages.append({"type": "http.request", "body": body, "more_body": not is_last})
    if not messages:
        messages.append({"type": "http.request", "body": b"", "more_body": False})
    it = iter(messages)

    async def receive():
        return next(it)

    return receive


def _make_request(
    *,
    method: str = "GET",
    path: str = "/",
    query_string: bytes = b"",
    path_params: dict[str, str] | None = None,
    headers: list[tuple[bytes, bytes]] | None = None,
    body: bytes = b"",
) -> Request:
    """Build a Request from minimal parameters."""
    scope = _make_scope(
        method=method,
        path=path,
        query_string=query_string,
        headers=headers or [],
    )
    return Request.from_asgi(scope, _make_receive(body), path_params=path_params or {})


@dataclass(frozen=True, slots=True)
class SearchParams:
    q: str = ""
    offset: int = 0


@dataclass(frozen=True, slots=True)
class FormData:
    message: str = ""


# ---------------------------------------------------------------------------
# resolve_kwargs tests
# ---------------------------------------------------------------------------


class TestResolveKwargsRequest:
    """resolve_kwargs injects request by name or annotation."""

    async def test_inject_by_name(self) -> None:
        def handler(request):
            pass

        req = _make_request()
        kwargs = await resolve_kwargs(handler, req, {}, {})
        assert kwargs["request"] is req

    async def test_inject_by_annotation(self) -> None:
        def handler(req: Request):
            pass

        req = _make_request()
        kwargs = await resolve_kwargs(handler, req, {}, {})
        assert kwargs["req"] is req


class TestResolveKwargsPathParams:
    """resolve_kwargs injects path params with type coercion."""

    async def test_string_path_param(self) -> None:
        def handler(doc_id: str):
            pass

        req = _make_request(path_params={"doc_id": "abc"})
        kwargs = await resolve_kwargs(handler, req, {}, {})
        assert kwargs["doc_id"] == "abc"

    async def test_int_coercion(self) -> None:
        def handler(item_id: int):
            pass

        req = _make_request(path_params={"item_id": "42"})
        kwargs = await resolve_kwargs(handler, req, {}, {})
        assert kwargs["item_id"] == 42

    async def test_coercion_failure_keeps_string(self) -> None:
        def handler(item_id: int):
            pass

        req = _make_request(path_params={"item_id": "not-a-number"})
        kwargs = await resolve_kwargs(handler, req, {}, {})
        assert kwargs["item_id"] == "not-a-number"

    async def test_unannotated_path_param(self) -> None:
        def handler(slug):
            pass

        req = _make_request(path_params={"slug": "hello-world"})
        kwargs = await resolve_kwargs(handler, req, {}, {})
        assert kwargs["slug"] == "hello-world"


class TestResolveKwargsCascadeContext:
    """resolve_kwargs injects values from cascade context."""

    async def test_cascade_value(self) -> None:
        def handler(doc):
            pass

        req = _make_request()
        kwargs = await resolve_kwargs(handler, req, {"doc": {"title": "Test"}}, {})
        assert kwargs["doc"] == {"title": "Test"}

    async def test_path_param_takes_priority(self) -> None:
        """Path params have higher priority than cascade context."""

        def handler(doc_id: str):
            pass

        req = _make_request(path_params={"doc_id": "from-path"})
        kwargs = await resolve_kwargs(
            handler,
            req,
            {"doc_id": "from-context"},
            {},
        )
        assert kwargs["doc_id"] == "from-path"


class TestResolveKwargsProviders:
    """resolve_kwargs injects service providers by annotation."""

    async def test_provider_injection(self) -> None:
        class Store:
            name = "real"

        store_instance = Store()

        def handler(store: Store):
            pass

        req = _make_request()
        kwargs = await resolve_kwargs(
            handler,
            req,
            {},
            {Store: lambda: store_instance},
        )
        assert kwargs["store"] is store_instance

    async def test_provider_factory_receives_request(self) -> None:
        """Factory with request param receives the current request."""

        def get_store(request: Request) -> object:
            return request

        def handler(store: object):
            pass

        req = _make_request()
        kwargs = await resolve_kwargs(
            handler,
            req,
            {},
            {object: get_store},
        )
        assert kwargs["store"] is req


class TestResolveKwargsExtraction:
    """resolve_kwargs extracts dataclasses from query (GET) and body (POST)."""

    async def test_get_extracts_from_query(self) -> None:
        def handler(params: SearchParams):
            pass

        req = _make_request(query_string=b"q=hello&offset=5")
        kwargs = await resolve_kwargs(handler, req, {}, {})
        assert isinstance(kwargs["params"], SearchParams)
        assert kwargs["params"].q == "hello"
        assert kwargs["params"].offset == 5

    async def test_post_extracts_from_form_body(self) -> None:
        def handler(data: FormData):
            pass

        req = _make_request(
            method="POST",
            headers=[
                (b"content-type", b"application/x-www-form-urlencoded"),
            ],
            body=b"message=hello+world",
        )
        kwargs = await resolve_kwargs(handler, req, {}, {})
        assert isinstance(kwargs["data"], FormData)
        assert kwargs["data"].message == "hello world"

    async def test_post_extracts_from_json_body(self) -> None:
        import json

        def handler(data: FormData):
            pass

        body = json.dumps({"message": "from json"}).encode()
        req = _make_request(
            method="POST",
            headers=[
                (b"content-type", b"application/json"),
            ],
            body=body,
        )
        kwargs = await resolve_kwargs(handler, req, {}, {})
        assert isinstance(kwargs["data"], FormData)
        assert kwargs["data"].message == "from json"


class TestResolveKwargsCombined:
    """resolve_kwargs handles mixed parameter sources."""

    async def test_request_path_param_and_context(self) -> None:
        def handler(request: Request, doc_id: str, doc):
            pass

        req = _make_request(path_params={"doc_id": "abc"})
        kwargs = await resolve_kwargs(
            handler,
            req,
            {"doc": {"title": "Test"}},
            {},
        )
        assert kwargs["request"] is req
        assert kwargs["doc_id"] == "abc"
        assert kwargs["doc"] == {"title": "Test"}


# ---------------------------------------------------------------------------
# upgrade_result tests
# ---------------------------------------------------------------------------


class TestUpgradeResult:
    """upgrade_result converts Page to LayoutPage, passes others through."""

    def test_page_to_layout_page(self) -> None:
        result = Page("page.html", "content", title="Home")
        cascade_ctx = {"nav": "main"}

        upgraded = upgrade_result(result, cascade_ctx, layout_chain=None, context_providers=())

        assert isinstance(upgraded, LayoutPage)
        assert upgraded.name == "page.html"
        assert upgraded.block_name == "content"
        # Page context merged with cascade context
        assert upgraded.context["title"] == "Home"
        assert upgraded.context["nav"] == "main"

    def test_page_root_block_is_preserved(self) -> None:
        result = Page("page.html", "panel", page_block_name="page_root", title="Home")

        upgraded = upgrade_result(result, {}, layout_chain=None, context_providers=())

        assert isinstance(upgraded, LayoutPage)
        assert upgraded.block_name == "panel"
        assert upgraded.page_block_name == "page_root"
        assert upgraded.effective_page_block_name == "page_root"

    def test_warns_when_page_content_has_no_page_root(self) -> None:
        result = Page("page.html", "page_content", title="Home")

        with pytest.warns(UserWarning, match="page_block_name='page_root'"):
            upgraded = upgrade_result(result, {}, layout_chain=None, context_providers=())

        assert isinstance(upgraded, LayoutPage)

    def test_page_context_overrides_cascade(self) -> None:
        """Page's own context takes precedence over cascade context."""
        result = Page("page.html", "content", title="Page Title")
        cascade_ctx = {"title": "Cascade Title", "extra": "value"}

        upgraded = upgrade_result(result, cascade_ctx, layout_chain=None, context_providers=())

        assert isinstance(upgraded, LayoutPage)
        assert upgraded.context["title"] == "Page Title"
        assert upgraded.context["extra"] == "value"

    def test_page_shell_actions_merge_with_cascade(self) -> None:
        result = Page(
            "page.html",
            "content",
            shell_actions=ShellActions(
                primary=ShellActionZone(
                    items=(ShellAction(id="reply", label="Reply", href="/reply"),),
                    remove=("new-thread",),
                )
            ),
        )
        cascade_ctx = {
            "shell_actions": ShellActions(
                primary=ShellActionZone(
                    items=(ShellAction(id="new-thread", label="New thread", href="/new"),)
                )
            )
        }

        upgraded = upgrade_result(result, cascade_ctx, layout_chain=None, context_providers=())

        assert isinstance(upgraded, LayoutPage)
        shell_actions = upgraded.context["shell_actions"]
        assert isinstance(shell_actions, ShellActions)
        assert [item.id for item in shell_actions.primary.items] == ["reply"]

    def test_layout_chain_passed_through(self) -> None:
        result = Page("page.html", "content")
        sentinel = object()  # stand-in for LayoutChain

        upgraded = upgrade_result(
            result,
            {},
            layout_chain=sentinel,
            context_providers=(),
        )

        assert isinstance(upgraded, LayoutPage)
        assert upgraded.layout_chain is sentinel

    def test_string_passes_through(self) -> None:
        result = upgrade_result("hello", {}, layout_chain=None, context_providers=())
        assert result == "hello"

    def test_dict_passes_through(self) -> None:
        result = upgrade_result({"key": "val"}, {}, layout_chain=None, context_providers=())
        assert result == {"key": "val"}

    def test_none_passes_through(self) -> None:
        result = upgrade_result(None, {}, layout_chain=None, context_providers=())
        assert result is None

    def test_oob_main_page_is_upgraded(self) -> None:
        result = OOB(Page("page.html", "content", title="Home"))

        upgraded = upgrade_result(result, {"nav": "main"}, layout_chain=None, context_providers=())

        assert isinstance(upgraded, OOB)
        assert isinstance(upgraded.main, LayoutPage)
        assert upgraded.main.context["title"] == "Home"
        assert upgraded.main.context["nav"] == "main"

    def test_suspense_to_layout_suspense_when_layout_chain_has_layouts(self) -> None:
        from chirp.pages.types import LayoutChain, LayoutInfo
        from chirp.templating.returns import LayoutSuspense, Suspense

        class _Delayed:
            def __await__(self):
                async def _coro():
                    return "done"

                return _coro().__await__()

        result = Suspense("dashboard.html", title="Home", stats=_Delayed())
        chain = LayoutChain(layouts=(LayoutInfo("_layout.html", "body", 0),))

        upgraded = upgrade_result(
            result,
            {"nav": "main"},
            layout_chain=chain,
            context_providers=(),
        )

        assert isinstance(upgraded, LayoutSuspense)
        assert upgraded.suspense is result
        assert upgraded.layout_chain is chain
        assert upgraded.context["title"] == "Home"
        assert upgraded.context["nav"] == "main"
        # awaitable replaced with None in layout context
        assert upgraded.context.get("stats") is None

    def test_suspense_passes_through_when_no_layout_chain(self) -> None:
        from chirp.templating.returns import Suspense

        result = Suspense("page.html", title="X")
        upgraded = upgrade_result(result, {}, layout_chain=None, context_providers=())
        assert upgraded is result

    def test_suspense_passes_through_when_layout_chain_empty(self) -> None:
        from chirp.templating.returns import Suspense

        result = Suspense("page.html", title="X")
        chain = LayoutChain(layouts=())
        upgraded = upgrade_result(result, {}, layout_chain=chain, context_providers=())
        assert upgraded is result

    def test_page_composition_gets_layout_chain_and_providers(self) -> None:
        """PageComposition with layout_chain=None gets discovered chain attached."""
        result = PageComposition(
            template="admin/page.html",
            fragment_block="page_content",
            page_block="page_root",
            context={"page_title": "Admin"},
        )
        chain = LayoutChain(layouts=(LayoutInfo("_layout.html", "body", 0),))
        provider = ContextProvider(module_path="/admin/_context.py", func=dict, depth=0)

        upgraded = upgrade_result(
            result,
            {"cascade_key": "value"},
            layout_chain=chain,
            context_providers=(provider,),
        )

        assert isinstance(upgraded, PageComposition)
        assert upgraded.layout_chain is chain
        assert upgraded.context_providers == (provider,)
        assert upgraded.context["page_title"] == "Admin"
        assert upgraded.context["cascade_key"] == "value"
        assert upgraded.template == "admin/page.html"
        assert upgraded.regions == ()

    def test_page_composition_preserves_explicit_chain(self) -> None:
        """PageComposition with explicit layout_chain keeps it unchanged."""
        chain = LayoutChain(layouts=(LayoutInfo("custom.html", "body", 0),))
        result = PageComposition(
            template="page.html",
            fragment_block="content",
            page_block="root",
            layout_chain=chain,
        )
        other_chain = LayoutChain(layouts=(LayoutInfo("_layout.html", "body", 0),))

        upgraded = upgrade_result(
            result,
            {},
            layout_chain=other_chain,
            context_providers=(),
        )

        assert upgraded.layout_chain is chain
