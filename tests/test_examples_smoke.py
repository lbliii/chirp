"""Every shipped example must actually boot, migrate, and serve.

The per-example ``test_app.py`` files assert *behavior* for the examples
that have them, and ``test_examples_contract_clean.py`` asserts every
example has a clean hypermedia contract. Neither catches the
*dead-on-first-call* / fake-implementation class: an example whose app
imports fine and passes the contract check but raises (or 500s) the moment
a real request hits it, or whose migrations never run so the first DB query
explodes.

This harness closes that gap. It discovers every ``examples/**/app.py`` and,
through the production-path ``chirp.testing.TestClient``:

1. confirms the app **boots** (loads + freezes under ``TestClient``);
2. if the app configures a ``Database``/migrations, points it at a throwaway
   sqlite file and runs migrations, asserting they apply cleanly;
3. discovers every parameterless GET route and GETs it, asserting the status
   is **not** 5xx and no exception escaped the handler -- a broken handler
   surfaces as a 500 (see ``test_broken_handler_is_caught_as_5xx``), so this
   assertion fails loudly when a route regresses.

Most examples pass on this zero-config default with no manifest. An optional
per-example ``example.toml`` (stdlib ``tomllib``) *augments* the default for
examples that need special handling -- see :class:`_Manifest` for the schema
and the ``examples/**/example.toml`` files for live usage. The harness mocks
all outbound ``httpx`` traffic (see :func:`_offline_httpx`) so LLM/network
examples stay deterministic and offline.

The watchdog will kill a run that boots all 46 examples at once, so validate
locally with ``-k`` for a representative subset; CI runs the full matrix.
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import sys
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from chirp.testing.client import TestClient
from chirp.testing.sse import assert_sse_wired

_EXAMPLES_ROOT = Path(__file__).resolve().parent.parent / "examples"
_APP_FILES = sorted(_EXAMPLES_ROOT.rglob("app.py"))
_IDS = [str(p.parent.relative_to(_EXAMPLES_ROOT)) for p in _APP_FILES]

# Framework-internal routes that exist on every app (dev reload, fragment
# loader). They are not example surface and must never be auto-smoked.
_FRAMEWORK_ROUTE_PREFIXES = ("/__chirp__", "/_frag")


# ---------------------------------------------------------------------------
# Optional per-example manifest (example.toml)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _RouteExpect:
    """An extra GET expectation beyond the auto-discovered smoke."""

    path: str
    status: int = 200
    contains: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class _MutationFlow:
    """A mutating request (POST/PUT/PATCH/DELETE) with expected outcome."""

    method: str
    path: str
    form: dict[str, str] = field(default_factory=dict)
    status: tuple[int, ...] = (200, 201, 204, 302, 303)
    contains: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class _SseExpect:
    """An SSE assertion: connect, collect, and (optionally) cross-check wiring."""

    path: str
    min_events: int = 1
    events: tuple[str, ...] = ()
    page: str | None = None  # if set, assert_sse_wired(page -> path)
    timeout: float = 3.0


@dataclass(frozen=True, slots=True)
class _Manifest:
    """Parsed ``example.toml``. Every field augments the zero-config default.

    Schema (all keys optional)::

        [env]
        STREAMING_FAST = "1"          # env vars set before the app is loaded

        skip = ["/needs-auth"]         # GET paths to drop from the auto-smoke

        [[routes]]                     # extra GET expectations
        path = "/api/health"
        status = 200
        contains = ["ok"]

        [[mutations]]                  # mutating flows
        method = "POST"
        path = "/todos"
        form = { text = "buy milk" }
        status = [200]
        contains = ["buy milk"]

        [[sse]]                        # SSE endpoints
        path = "/events"
        min_events = 1
        events = ["status"]
        page = "/"                     # optional: cross-check sse wiring
    """

    env: dict[str, str] = field(default_factory=dict)
    skip: tuple[str, ...] = ()
    routes: tuple[_RouteExpect, ...] = ()
    mutations: tuple[_MutationFlow, ...] = ()
    sse: tuple[_SseExpect, ...] = ()


def _load_manifest(app_path: Path) -> _Manifest:
    """Load the sibling ``example.toml`` if present, else an empty manifest."""
    toml_path = app_path.parent / "example.toml"
    if not toml_path.exists():
        return _Manifest()
    with toml_path.open("rb") as fh:
        raw = tomllib.load(fh)

    env = {str(k): str(v) for k, v in raw.get("env", {}).items()}
    skip = tuple(raw.get("skip", ()))
    routes = tuple(
        _RouteExpect(
            path=r["path"],
            status=int(r.get("status", 200)),
            contains=tuple(r.get("contains", ())),
        )
        for r in raw.get("routes", ())
    )
    mutations = tuple(
        _MutationFlow(
            method=str(m["method"]).upper(),
            path=m["path"],
            form={str(k): str(v) for k, v in m.get("form", {}).items()},
            status=tuple(m["status"]) if "status" in m else (200, 201, 204, 302, 303),
            contains=tuple(m.get("contains", ())),
        )
        for m in raw.get("mutations", ())
    )
    sse = tuple(
        _SseExpect(
            path=s["path"],
            min_events=int(s.get("min_events", 1)),
            events=tuple(s.get("events", ())),
            page=s.get("page"),
            timeout=float(s.get("timeout", 3.0)),
        )
        for s in raw.get("sse", ())
    )
    return _Manifest(env=env, skip=skip, routes=routes, mutations=mutations, sse=sse)


# ---------------------------------------------------------------------------
# Isolated example loading (mirrors tests/test_examples_contract_clean.py)
# ---------------------------------------------------------------------------


def _purge_example_modules() -> None:
    """Drop any cached module loaded from under ``examples/``.

    Examples ship local helper modules imported as top-level names (``store``,
    ``models``, ...). Python caches modules by name, so one example's ``store``
    would otherwise shadow every other example's. Purge before and after each
    load so each example resolves its own helpers against a clean slate.
    """
    examples_root = str(_EXAMPLES_ROOT)
    for name, mod in list(sys.modules.items()):
        mod_file = getattr(mod, "__file__", None)
        if mod_file and mod_file.startswith(examples_root):
            sys.modules.pop(name, None)


@dataclass(slots=True)
class _LoadedExample:
    app: Any
    module_name: str
    before_modules: set[str]
    before_path: list[str]


def _load_isolated(app_path: Path) -> _LoadedExample:
    """Load an example's ``app`` with sys.modules/sys.path isolation."""
    _purge_example_modules()
    before_modules = set(sys.modules)
    before_path = sys.path[:]
    sys.path.insert(0, str(app_path.parent))
    module_name = f"example_smoke_{app_path.parent.name}"
    spec = importlib.util.spec_from_file_location(module_name, app_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        with (
            contextlib.redirect_stdout(io.StringIO()),
            contextlib.redirect_stderr(io.StringIO()),
        ):
            spec.loader.exec_module(module)
    except BaseException:
        _unwind(module_name, before_modules, before_path)
        raise
    app = getattr(module, "app", None)
    return _LoadedExample(
        app=app,
        module_name=module_name,
        before_modules=before_modules,
        before_path=before_path,
    )


def _unwind(module_name: str, before_modules: set[str], before_path: list[str]) -> None:
    """Restore sys.path and purge anything the example load introduced."""
    sys.path[:] = before_path
    examples_root = str(_EXAMPLES_ROOT)
    for name in set(sys.modules) - before_modules:
        mod: ModuleType | None = sys.modules.get(name)
        mod_file = getattr(mod, "__file__", None)
        if name == module_name or (mod_file and mod_file.startswith(examples_root)):
            sys.modules.pop(name, None)


# ---------------------------------------------------------------------------
# Throwaway database redirection
# ---------------------------------------------------------------------------


def _redirect_db_to_tempfile(app: Any, tmp_path: Path) -> bool:
    """Point a file-backed sqlite ``Database`` at a throwaway file.

    Examples that configure ``App(db="sqlite:///...", migrations=...)`` build
    the ``Database`` at import time against a fixed path. We swap in a fresh
    ``Database`` over a temp file so the smoke run never touches (or creates)
    the example's real ``.db``, and so migrations + seed data run from scratch
    every time. ``TestClient.__aenter__`` connects and migrates the swapped DB.

    Returns ``True`` when the app uses a DB (so migration assertions run),
    else ``False``. In-memory sqlite (``:memory:``) and non-sqlite URLs are
    left untouched but still reported as DB-backed.
    """
    db = getattr(app, "_db", None)
    if db is None:
        return False
    from chirp.data.database import Database

    url = getattr(getattr(db, "_config", None), "url", "")
    if not url.startswith("sqlite:///") or ":memory:" in url:
        return True

    new_path = tmp_path / "smoke.db"
    new_db = Database(f"sqlite:///{new_path}")
    app._db = new_db
    app._mutable_state.db = new_db
    return True


# ---------------------------------------------------------------------------
# Offline httpx guard
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _offline_httpx(monkeypatch: pytest.MonkeyPatch) -> None:
    """Force every ``httpx.AsyncClient`` onto a benign in-process transport.

    LLM / API examples (``ollama``, ``hackernews``, ``rag_demo``,
    ``llm_playground``) create real ``httpx.AsyncClient`` instances. Without
    this, smoking their pages would either hit the network (non-deterministic)
    or block on connection timeouts. We override the transport so any request
    resolves instantly to ``200`` with an empty JSON body -- enough for the
    handlers' offline/empty-state code paths, never a real socket.
    """
    httpx = pytest.importorskip("httpx")

    def _benign(request: Any) -> Any:
        return httpx.Response(200, json=[])

    real_init = httpx.AsyncClient.__init__

    def _patched_init(self: Any, *args: Any, **kwargs: Any) -> None:
        kwargs["transport"] = httpx.MockTransport(_benign)
        real_init(self, *args, **kwargs)

    monkeypatch.setattr(httpx.AsyncClient, "__init__", _patched_init)


# ---------------------------------------------------------------------------
# Route discovery
# ---------------------------------------------------------------------------


def _auto_get_paths(app: Any, skip: tuple[str, ...]) -> list[str]:
    """Parameterless, directly-navigable GET paths to smoke.

    Excludes:
      - non-GET-only routes,
      - parametric paths (``{id}``) -- no value to fill,
      - ``referenced=True`` routes -- SSE streams / htmx-only surfaces that
        either run forever or are not meant for direct navigation,
      - framework-internal routes (dev reload, fragment loader),
      - anything in the manifest ``skip`` list.
    """
    skip_set = set(skip)
    seen: set[str] = set()
    paths: list[str] = []
    for route in sorted(app._router.routes, key=lambda r: r.path):
        if "GET" not in route.methods:
            continue
        if "{" in route.path:
            continue
        if route.referenced:
            continue
        if route.path.startswith(_FRAMEWORK_ROUTE_PREFIXES):
            continue
        if route.path in skip_set or route.path in seen:
            continue
        seen.add(route.path)
        paths.append(route.path)
    return paths


# ---------------------------------------------------------------------------
# The smoke test
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("app_path", _APP_FILES, ids=_IDS)
async def test_example_boots_migrates_and_serves(
    app_path: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rel = app_path.parent.relative_to(_EXAMPLES_ROOT)
    manifest = _load_manifest(app_path)

    for key, value in manifest.env.items():
        monkeypatch.setenv(key, value)

    loaded = _load_isolated(app_path)
    try:
        app = loaded.app
        assert app is not None, f"{rel}: app.py defines no top-level `app`"

        uses_db = _redirect_db_to_tempfile(app, tmp_path)

        # Boot: TestClient.__aenter__ freezes, connects the (redirected) DB, and
        # runs migrations. If migrations fail it raises here, failing the test.
        async with TestClient(app) as client:
            if uses_db:
                # Migrations ran during __aenter__; confirm the tracking table
                # exists so a no-op/silently-skipped migration step is caught.
                from chirp.data.migrate import _TRACKING_TABLE

                applied = await app.db.fetch_val(
                    "SELECT COUNT(*) FROM sqlite_master WHERE type = 'table' AND name = ?",
                    _TRACKING_TABLE,
                )
                assert applied == 1, (
                    f"{rel}: app configures a database but the migration "
                    f"tracking table {_TRACKING_TABLE!r} was never created -- "
                    "migrations did not run."
                )

            # (3) Auto-smoke every parameterless GET route: never 5xx.
            get_paths = _auto_get_paths(app, manifest.skip)
            # Most examples expose at least one directly-navigable GET route.
            # A few (e.g. a static-files-only app served entirely by
            # StaticFiles middleware) have no app routes at all -- those must
            # declare their smoke surface explicitly in the manifest so the
            # example still has *some* asserted surface and cannot pass on a
            # vacuous boot alone.
            manifest_surface = bool(manifest.routes or manifest.mutations or manifest.sse)
            assert get_paths or manifest_surface, (
                f"{rel}: no directly-navigable GET routes discovered and no "
                "manifest surface (routes/mutations/sse) declared -- the "
                "example would pass on a vacuous boot. Add an example.toml "
                "with explicit expectations (e.g. a StaticFiles-only app)."
            )
            for path in get_paths:
                response = await client.get(path)
                assert response.status < 500, (
                    f"{rel}: GET {path} returned {response.status} "
                    f"(5xx -- handler raised or render failed).\n"
                    f"Body: {response.text[:400]}"
                )

            # Manifest: extra GET expectations with explicit status + markers.
            for expect in manifest.routes:
                response = await client.get(expect.path)
                assert response.status == expect.status, (
                    f"{rel}: GET {expect.path} expected status "
                    f"{expect.status}, got {response.status}.\n"
                    f"Body: {response.text[:400]}"
                )
                for needle in expect.contains:
                    assert needle in response.text, (
                        f"{rel}: GET {expect.path} body missing {needle!r}.\n"
                        f"Body: {response.text[:400]}"
                    )

            # Manifest: mutating flows (POST/PUT/PATCH/DELETE).
            for flow in manifest.mutations:
                response = await client.request(
                    flow.method,
                    flow.path,
                    body=_encode_form(flow.form) if flow.form else None,
                    headers=(
                        {"content-type": "application/x-www-form-urlencoded"} if flow.form else None
                    ),
                )
                assert response.status in flow.status, (
                    f"{rel}: {flow.method} {flow.path} expected status in "
                    f"{flow.status}, got {response.status}.\n"
                    f"Body: {response.text[:400]}"
                )
                for needle in flow.contains:
                    assert needle in response.text, (
                        f"{rel}: {flow.method} {flow.path} body missing "
                        f"{needle!r}.\nBody: {response.text[:400]}"
                    )

            # Manifest: SSE endpoints.
            for sse in manifest.sse:
                if sse.page is not None and sse.events:
                    await assert_sse_wired(
                        client,
                        sse.page,
                        sse.path,
                        max_events=max(sse.min_events, len(sse.events)),
                    )
                result = await client.sse(
                    sse.path,
                    max_events=max(sse.min_events, len(sse.events) or 1),
                    timeout=sse.timeout,
                )
                assert result.status == 200, (
                    f"{rel}: SSE {sse.path} responded {result.status}, not 200."
                )
                assert len(result.events) >= sse.min_events, (
                    f"{rel}: SSE {sse.path} produced {len(result.events)} "
                    f"event(s), expected at least {sse.min_events}."
                )
                emitted = {evt.event or "message" for evt in result.events}
                for name in sse.events:
                    assert name in emitted, (
                        f"{rel}: SSE {sse.path} never emitted event {name!r} "
                        f"(emitted: {sorted(emitted)})."
                    )
    finally:
        _unwind(loaded.module_name, loaded.before_modules, loaded.before_path)
        _purge_example_modules()


def _encode_form(form: dict[str, str]) -> bytes:
    from urllib.parse import urlencode

    return urlencode(form, doseq=True).encode("utf-8")


# ---------------------------------------------------------------------------
# Meta-tests -- guard the harness itself so it can't pass vacuously
# ---------------------------------------------------------------------------


def test_discovered_all_examples() -> None:
    """Guard against the glob silently matching nothing (e.g. a moved dir)."""
    assert len(_APP_FILES) >= 40, (
        f"Only discovered {len(_APP_FILES)} example app.py files -- "
        "the examples/ layout may have moved."
    )


def test_manifests_parse() -> None:
    """Every shipped ``example.toml`` must parse into a valid manifest.

    A typo'd manifest that silently failed to load would weaken the example
    it covers (e.g. an SSE assertion that never runs), so fail loud here.
    """
    toml_files = sorted(_EXAMPLES_ROOT.rglob("example.toml"))
    assert toml_files, "No example.toml manifests found -- expected at least one."
    for toml_path in toml_files:
        manifest = _load_manifest(toml_path.parent / "app.py")
        assert isinstance(manifest, _Manifest)


async def test_broken_handler_is_caught_as_5xx() -> None:
    """The auto-smoke's ``status < 500`` assertion must actually catch breakage.

    Proves the test is meaningful: a handler that raises produces a 500, which
    the smoke loop rejects. If the framework ever stopped surfacing handler
    exceptions as 5xx, this guard fails and the smoke would be revealed as
    vacuous.
    """
    from chirp import App, AppConfig

    app = App(config=AppConfig())

    @app.route("/boom")
    def boom() -> str:
        raise RuntimeError("kaboom")

    async with TestClient(app) as client:
        response = await client.get("/boom")
    assert response.status >= 500, (
        "A raising handler no longer surfaces as 5xx -- the smoke loop's "
        "`status < 500` assertion would pass vacuously."
    )
