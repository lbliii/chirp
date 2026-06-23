"""Orchestrator-wiring proofs for individual contract rules.

The per-rule modules (``test_csp_nonce_rule.py``, ``test_reactive.py``,
``test_islands.py``, ``test_sse.py``, ``test_accessibility.py``,
``test_data_shapes_rule.py``, ``test_suspense_defer_rule.py``) exercise each
``check_*`` function by **direct call**. That proves the rule *logic* is correct
but says nothing about whether ``check_hypermedia_surface`` (the single
orchestrator that ``app.check()`` runs) actually *invokes* the rule. A
regression that drops a ``result.issues.extend(check_...)`` line from
``checker.py`` would leave every direct-call unit test green while silently
disabling the rule for real apps.

This module closes that gap. For each rule it builds a **minimal real App**
whose config/templates TRIGGER the rule and asserts the expected category
appears in ``check_hypermedia_surface(app).issues``; a paired clean app proves
the assertion is not vacuous (and would catch a rule that fires unconditionally).
If a rule is unwired from the orchestrator, the firing assertion fails.

Mirrors ``test_deploy_nojs_i18n_integration.py``: real ``App`` + ``Router`` +
``check_hypermedia_surface``, category presence/absence only.
"""

from dataclasses import dataclass

import pytest

from chirp import App
from chirp.config import AppConfig
from chirp.contracts import check_hypermedia_surface
from chirp.contracts.types import Severity
from chirp.data import nested, shape


def _issues(app: App) -> list:
    return check_hypermedia_surface(app).issues


def _categories(app: App) -> set[str]:
    return {issue.category for issue in _issues(app)}


# ---------------------------------------------------------------------------
# csp_nonce (#181 / #195) -- inline-forbidding CSP, no nonce mechanism, in prod
# ---------------------------------------------------------------------------

# A nonce-only / inline-forbidding CSP (script-src without 'unsafe-inline').
_NONCE_CSP = "default-src 'self'; script-src 'self' https://cdn.jsdelivr.net"


def _csp_nonce_app(tmp_path, **config_overrides) -> App:
    (tmp_path / "index.html").write_text("<div id='x'></div>", encoding="utf-8")
    from chirp.middleware.security_headers import (
        SecurityHeadersConfig,
        SecurityHeadersMiddleware,
    )

    app = App(
        AppConfig(
            skip_contract_checks=True,
            template_dir=str(tmp_path),
            env="production",
            secret_key="x" * 32,
            # alpine=True is a framework inline-script feature, so the
            # un-nonceable case actually breaks something.
            alpine=True,
            **config_overrides,
        )
    )
    # A static inline-forbidding CSP with NO CSPNonceMiddleware: csp_nonce()
    # returns "" and the framework inline scripts emit un-nonced.
    app.add_middleware(
        SecurityHeadersMiddleware(SecurityHeadersConfig(content_security_policy=_NONCE_CSP))
    )

    @app.route("/")
    def index():
        return "ok"

    return app


def test_csp_nonce_fires_for_unnonceable_inline_in_production(tmp_path) -> None:
    """Production + inline-forbidding CSP + no nonce mechanism + inline feature
    -> the csp_nonce rule must reach ``result.issues`` as an ERROR through the
    orchestrator. Drop the ``check_csp_nonce`` wiring and this fails."""
    app = _csp_nonce_app(tmp_path)
    csp = [i for i in _issues(app) if i.category == "csp_nonce"]
    assert csp, "csp_nonce did not fire through check_hypermedia_surface"
    assert any(i.severity is Severity.ERROR for i in csp)


def test_csp_nonce_silent_when_nonce_mechanism_enabled(tmp_path) -> None:
    """Negative control: the same forbidding CSP + ``csp_nonce_enabled=True``
    (auto-wires the per-request nonce) makes every inline script nonceable, so
    the rule stays silent. Proves the firing test is gated on the nonce
    mechanism, not vacuously true."""
    app = _csp_nonce_app(tmp_path, csp_nonce_enabled=True)
    assert "csp_nonce" not in _categories(app)


# ---------------------------------------------------------------------------
# accessibility -- a11y_alt on a real template scanned by the orchestrator
# ---------------------------------------------------------------------------


def _accessibility_app(tmp_path, template_html: str) -> App:
    (tmp_path / "index.html").write_text(template_html, encoding="utf-8")
    app = App(AppConfig(skip_contract_checks=True, template_dir=str(tmp_path)))

    @app.route("/")
    def index():
        from chirp.templating.returns import Template

        return Template("index.html")

    return app


def test_accessibility_fires_for_img_without_alt(tmp_path) -> None:
    """An <img> with no alt attribute -> a11y_alt WARNING, proving the
    per-template accessibility checks run inside the orchestrator's template
    scan loop."""
    app = _accessibility_app(tmp_path, '<div id="x"><img src="/logo.png"></div>')
    a11y = [i for i in _issues(app) if i.category == "a11y_alt"]
    assert a11y, "a11y_alt did not fire through check_hypermedia_surface"
    assert all(i.severity is Severity.WARNING for i in a11y)


def test_accessibility_silent_when_alt_present(tmp_path) -> None:
    """Negative control: the same <img> with alt set -> no a11y_alt issue."""
    app = _accessibility_app(tmp_path, '<div id="x"><img src="/logo.png" alt="Logo"></div>')
    assert "a11y_alt" not in _categories(app)


# ---------------------------------------------------------------------------
# islands (strict) -- strict-mode mount metadata flows from config into the rule
# ---------------------------------------------------------------------------

# A mount with no id and no version: only WARNS under islands_contract_strict.
_ISLAND_NO_ID = '<div id="x"><div data-island="editor"></div></div>'


def _islands_app(tmp_path, *, strict: bool) -> App:
    (tmp_path / "index.html").write_text(_ISLAND_NO_ID, encoding="utf-8")
    app = App(
        AppConfig(
            skip_contract_checks=True,
            template_dir=str(tmp_path),
            islands=True,
            islands_contract_strict=strict,
        )
    )

    @app.route("/")
    def index():
        from chirp.templating.returns import Template

        return Template("index.html")

    return app


def test_islands_strict_fires_for_missing_mount_id(tmp_path) -> None:
    """With islands_contract_strict=True, a data-island mount lacking a stable
    id WARNS. Proves both that check_island_mounts is wired AND that the strict
    flag is plumbed from AppConfig through the snapshot into the rule call."""
    app = _islands_app(tmp_path, strict=True)
    islands = [i for i in _issues(app) if i.category == "islands"]
    assert islands, "islands (strict) did not fire through check_hypermedia_surface"
    assert any("mount id" in i.message for i in islands)


def test_islands_silent_when_strict_disabled(tmp_path) -> None:
    """Negative control: islands_contract_strict=False -> the same mount is
    clean. If this fired, the strict flag would not be reaching the rule."""
    app = _islands_app(tmp_path, strict=False)
    assert "islands" not in _categories(app)


# ---------------------------------------------------------------------------
# sse -- sse-swap on the sse-connect element (template-scan rule)
# ---------------------------------------------------------------------------

_SSE_SELF_SWAP = (
    '<div id="x" hx-ext="sse" sse-connect="/events" sse-swap="message" hx-swap="beforeend"></div>'
)
_SSE_CHILD_SWAP = (
    '<div id="x" hx-ext="sse" sse-connect="/events">'
    '<span sse-swap="message" hx-swap="beforeend"></span></div>'
)


def _sse_app(tmp_path, template_html: str) -> App:
    (tmp_path / "index.html").write_text(template_html, encoding="utf-8")
    app = App(AppConfig(skip_contract_checks=True, template_dir=str(tmp_path)))

    @app.route("/")
    def index():
        from chirp.templating.returns import Template

        return Template("index.html")

    return app


def test_sse_fires_for_self_swap(tmp_path) -> None:
    """sse-swap on the same element as sse-connect -> sse_self_swap ERROR,
    proving check_sse_self_swap is wired into the orchestrator."""
    app = _sse_app(tmp_path, _SSE_SELF_SWAP)
    sse = [i for i in _issues(app) if i.category == "sse_self_swap"]
    assert sse, "sse_self_swap did not fire through check_hypermedia_surface"
    assert all(i.severity is Severity.ERROR for i in sse)


def test_sse_silent_when_swap_on_child(tmp_path) -> None:
    """Negative control: sse-swap on a child element is valid -> no issue."""
    app = _sse_app(tmp_path, _SSE_CHILD_SWAP)
    assert "sse_self_swap" not in _categories(app)


# ---------------------------------------------------------------------------
# reactive_block -- DependencyIndex BlockRef to a missing block
# ---------------------------------------------------------------------------


def _reactive_app(tmp_path, *, register_index: bool) -> App:
    (tmp_path / "board.html").write_text(
        "{% block task_list %}<ul></ul>{% endblock %}",
        encoding="utf-8",
    )
    app = App(AppConfig(skip_contract_checks=True, template_dir=str(tmp_path)))

    @app.route("/")
    def index():
        from chirp.templating.returns import Template

        return Template("board.html")

    if register_index:
        from chirp.pages.reactive.events import BlockRef
        from chirp.pages.reactive.index import DependencyIndex

        index = DependencyIndex()
        # Typo: the template defines "task_list", not "taks_list".
        index.register("tasks", BlockRef(template_name="board.html", block_name="taks_list"))
        # The orchestrator reads the index from extras when the app has no
        # private _reactive_index attribute (see checker.py).
        app.set_contract_check_data("reactive_index", index)

    return app


def test_reactive_block_fires_for_missing_block(tmp_path) -> None:
    """A registered DependencyIndex with a BlockRef to a nonexistent block ->
    reactive_block ERROR. Proves the orchestrator picks up the index from
    snapshot.extras and runs check_reactive_block_existence."""
    app = _reactive_app(tmp_path, register_index=True)
    reactive = [i for i in _issues(app) if i.category == "reactive_block"]
    assert reactive, "reactive_block did not fire through check_hypermedia_surface"
    assert all(i.severity is Severity.ERROR for i in reactive)
    assert any("taks_list" in i.message for i in reactive)


def test_reactive_block_silent_without_index(tmp_path) -> None:
    """Negative control: no DependencyIndex registered -> the reactive checks
    are gated off (``if reactive_index is not None``) and nothing fires."""
    app = _reactive_app(tmp_path, register_index=False)
    assert "reactive_block" not in _categories(app)


# ---------------------------------------------------------------------------
# data (#159) -- typed-SQL column drift, requires a real db + migrations
# ---------------------------------------------------------------------------


# Module-level so the handler's __globals__ can resolve the cls name.
@dataclass(frozen=True, slots=True)
class _User:
    id: int
    name: str


def _data_app(tmp_path) -> App:
    """A db-backed App with a ``users`` schema and no fetch route yet.

    Each test registers its own handler with a **string-literal** SQL in the
    body: check_data_shapes only analyzes literal SQL, so passing the query
    through a closure variable would make the rule (correctly) skip it.
    """
    template_dir = tmp_path / "templates"
    template_dir.mkdir()
    (template_dir / "page.html").write_text("<html><body>hi</body></html>", encoding="utf-8")
    migrations = tmp_path / "migrations"
    migrations.mkdir()
    (migrations / "001_users.sql").write_text(
        "CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT);",
        encoding="utf-8",
    )
    return App(
        db="sqlite:///:memory:",
        migrations=str(migrations),
        config=AppConfig(skip_contract_checks=True, template_dir=str(template_dir)),
    )


def test_data_fires_for_drifted_column(tmp_path) -> None:
    """db.fetch selecting a column that maps to no dataclass field nor schema
    column -> data ERROR. Proves check_data_shapes is wired AND that the
    declared schema reaches the rule (a column unknown to both is flagged)."""
    app = _data_app(tmp_path)

    @app.route("/users")
    async def users():
        from chirp.data import get_db
        from chirp.templating.returns import Template

        db = get_db()
        await db.fetch(_User, "SELECT id, naem FROM users")  # typo: naem
        return Template("page.html")

    data = [i for i in _issues(app) if i.category == "data"]
    assert data, "data (#159) did not fire through check_hypermedia_surface"
    assert all(i.severity is Severity.ERROR for i in data)
    assert any("naem" in i.message for i in data)


def test_data_silent_for_matching_columns(tmp_path) -> None:
    """Negative control: every SELECTed column maps to a dataclass field -> no
    data issue (same db/schema, correct column names)."""
    app = _data_app(tmp_path)

    @app.route("/users")
    async def users():
        from chirp.data import get_db
        from chirp.templating.returns import Template

        db = get_db()
        await db.fetch(_User, "SELECT id, name FROM users")
        return Template("page.html")

    assert "data" not in _categories(app)


# ---------------------------------------------------------------------------
# suspense_defer (#180) -- declared deferred key no block depends on
# ---------------------------------------------------------------------------

# The shell self-declares "stats" as deferred via __chirp_defer_pending__, but
# no block's depends_on references "stats", so auto-discovery finds nothing to
# re-render -> WARNING.
_SUSPENSE_UNDISCOVERABLE = (
    "<html><body>"
    "{% block shell %}"
    '{% if "stats" in __chirp_defer_pending__ %}<p>loading</p>{% endif %}'
    "{% endblock %}"
    "</body></html>"
)
# Clean: a block actually depends on "stats", so discovery finds it.
_SUSPENSE_DISCOVERABLE = (
    "<html><body>"
    "{% block shell %}"
    '{% if "stats" in __chirp_defer_pending__ %}<p>loading</p>{% endif %}'
    "{% endblock %}"
    "{% block stats_panel %}{{ stats }}{% endblock %}"
    "</body></html>"
)


def _suspense_app(tmp_path, template_html: str) -> App:
    (tmp_path / "page.html").write_text(template_html, encoding="utf-8")
    app = App(AppConfig(skip_contract_checks=True, template_dir=str(tmp_path)))

    @app.route("/")
    def index():
        from chirp.templating.returns import Template

        return Template("page.html")

    return app


def test_suspense_defer_fires_for_undiscoverable_key(tmp_path) -> None:
    """A template self-declaring a deferred key that no block depends on ->
    suspense_defer WARNING. Proves check_suspense_undiscoverable is wired."""
    app = _suspense_app(tmp_path, _SUSPENSE_UNDISCOVERABLE)
    suspense = [i for i in _issues(app) if i.category == "suspense_defer"]
    assert suspense, "suspense_defer (#180) did not fire through check_hypermedia_surface"
    assert all(i.severity is Severity.WARNING for i in suspense)
    assert any("stats" in i.message for i in suspense)


def test_suspense_defer_silent_when_block_depends_on_key(tmp_path) -> None:
    """Negative control: a block depends on the deferred key, so auto-discovery
    finds it and the rule stays silent."""
    app = _suspense_app(tmp_path, _SUSPENSE_DISCOVERABLE)
    assert "suspense_defer" not in _categories(app)


# ---------------------------------------------------------------------------
# shapecheck (#166/#168/#173) -- surface-contract registry drift
# ---------------------------------------------------------------------------


def _shapecheck_app(tmp_path, *, drift: bool) -> App:
    """A db-less App; the firing case registers a surface contract naming a
    Shape that does not exist (registry drift -- the headline check)."""
    (tmp_path / "index.html").write_text("<div id='x'></div>", encoding="utf-8")
    app = App(AppConfig(skip_contract_checks=True, template_dir=str(tmp_path)))

    @app.route("/")
    def index():
        from chirp.templating.returns import Template

        return Template("index.html")

    if drift:
        # No @shape named "MissingBoardSurface" is registered anywhere in the
        # suite -> drift ERROR. Runs even with no Shape bindings on the routes.
        app.set_contract_check_data("surface_contracts", {"home-board": "MissingBoardSurface"})

    return app


def test_shapecheck_fires_for_registry_drift(tmp_path) -> None:
    """A surface-contract registry name with no backing Shape -> shapecheck
    ERROR through the orchestrator. Drop the ``check_shapecheck`` wiring and this
    fails. Proves the rule runs even for a db-less, Shape-less app via the auto
    ``shape_registry()`` (and that extras flow into the rule)."""
    app = _shapecheck_app(tmp_path, drift=True)
    shapecheck = [i for i in _issues(app) if i.category == "shapecheck"]
    assert shapecheck, "shapecheck did not fire through check_hypermedia_surface"
    assert any(i.severity is Severity.ERROR for i in shapecheck)
    assert any("MissingBoardSurface" in i.message for i in shapecheck)


def test_shapecheck_silent_for_clean_app(tmp_path) -> None:
    """Negative control: no surface contracts, no Shape bindings -> no
    shapecheck issue at all (not even a PASS line, since nothing is verified)."""
    app = _shapecheck_app(tmp_path, drift=False)
    assert "shapecheck" not in _categories(app)


# ---------------------------------------------------------------------------
# shapecheck (#167/#169) -- Shape.validate fail-loud + nested-field no-false-ERROR
# through the orchestrator. These prove the #3 wiring (Shape.validate over every
# USED Shape) AND the #1 nested-field union, end-to-end through app.check().
# ---------------------------------------------------------------------------


# A child Shape that does NOT carry its ``on`` join column as a field. The parent
# declares it nested -> Shape.validate rejects the parent as un-compilable.
@shape("SELECT id, name FROM wiring_bad_cards WHERE x = :x")
@dataclass(frozen=True, slots=True)
class _WiringBadCard:
    id: int
    name: str


@shape("SELECT id, title FROM wiring_bad_boards WHERE id = :id")
@dataclass(frozen=True, slots=True)
class _WiringBadBoard:
    id: int
    title: str
    cards: tuple = nested(_WiringBadCard, on="board_id", key="id")


# A well-formed nested Shape pair: the child carries ``board_id`` (its ``on``),
# the parent carries ``id`` (the ``key``). No malformation -> validate passes.
@shape("SELECT id, name, board_id FROM wiring_ok_cards WHERE board_id = :bid")
@dataclass(frozen=True, slots=True)
class _WiringOkCard:
    id: int
    name: str
    board_id: int


@shape("SELECT id, title FROM wiring_ok_boards WHERE id = :id")
@dataclass(frozen=True, slots=True)
class _WiringOkBoard:
    id: int
    title: str
    cards: tuple = nested(_WiringOkCard, on="board_id", key="id")


def _nested_shape_app(tmp_path, *, malformed: bool) -> App:
    """A db-less App whose one route binds a (malformed or clean) nested Shape.

    The handler references a module-level Shape name DIRECTLY (not via a closure
    variable) so ``inspect.getsource`` + the static binding walk -- which
    resolves the first ``Shape.fetch`` arg against the handler's ``__globals__``
    -- recover the route -> Shape binding, marking the Shape "used" for the
    ``Shape.validate`` pass.
    """
    (tmp_path / "board.html").write_text(
        "{% block detail %}<h1>{{ board.title }}</h1>"
        "<ul>{% for c in board.cards %}<li>{{ c.name }}</li>{% endfor %}</ul>"
        "<p>{{ board.id }}</p>{% endblock %}",
        encoding="utf-8",
    )
    app = App(AppConfig(skip_contract_checks=True, template_dir=str(tmp_path)))

    if malformed:

        @app.route("/b")
        def board_bad():
            from chirp.data import Shape, get_db
            from chirp.templating.returns import Fragment

            db = get_db()
            rows = Shape.fetch(_WiringBadBoard, db, id=1)
            return Fragment("board.html", "detail", board=rows)
    else:

        @app.route("/b")
        def board_ok():
            from chirp.data import Shape, get_db
            from chirp.templating.returns import Fragment

            db = get_db()
            rows = Shape.fetch(_WiringOkBoard, db, id=1)
            return Fragment("board.html", "detail", board=rows)

    return app


def test_shapecheck_fires_for_malformed_nested_shape(tmp_path) -> None:
    """A route binds a Shape whose nested() child cannot be batched (missing the
    ``on`` join column as a field). ``Shape.validate`` raises ShapeError, which
    the orchestrator-wired ``_check_shape_validate`` pass surfaces as a
    shapecheck ERROR. Proves #3 wiring (Shape.validate over every USED Shape)
    reaches ``check_hypermedia_surface``. Drop that wiring and this fails."""
    app = _nested_shape_app(tmp_path, malformed=True)
    errors = [
        i for i in _issues(app) if i.category == "shapecheck" and i.severity is Severity.ERROR
    ]
    assert errors, "Shape.validate fail-loud did not reach check_hypermedia_surface"
    assert any("_WiringBadBoard" in i.message for i in errors)
    assert any("board_id" in i.message for i in errors)


def test_shapecheck_no_false_underfetch_for_nested_field(tmp_path) -> None:
    """A realistic nested-Shape app: a block iterates ``board.cards`` (a
    ``nested()`` field, NOT a SELECT column). Through ``app.check()`` this must
    produce NO false under-fetch ERROR (#1 nested-field union) and NO
    ``Shape.validate`` failure (#3, the child is well-formed) -- only a clean
    PASS. Negative control proving the firing test is not vacuous."""
    app = _nested_shape_app(tmp_path, malformed=False)
    shapecheck = [i for i in _issues(app) if i.category == "shapecheck"]
    assert not [i for i in shapecheck if i.severity is Severity.ERROR], [
        i.message for i in shapecheck if i.severity is Severity.ERROR
    ]
    # The binding was verified clean -> a PASS line surfaces.
    assert any(i.severity is Severity.INFO for i in shapecheck)


# ---------------------------------------------------------------------------
# macro_css (#148 child 1) -- core macro classes with no backing CSS, chirp-ui off
# ---------------------------------------------------------------------------

# A template emitting a core-macro dangling class with chirp-ui NOT active.
_MACRO_CSS_DANGLING = (
    '<div id="x" class="chirp-dropdown"><button class="chirp-dropdown-trigger"></button></div>'
)
# Clean: a custom class that does not collide with any core-macro token.
_MACRO_CSS_CLEAN = '<div id="x" class="my-dropdown"><button class="my-trigger"></button></div>'


def _macro_css_app(tmp_path, template_html: str) -> App:
    (tmp_path / "index.html").write_text(template_html, encoding="utf-8")
    app = App(AppConfig(skip_contract_checks=True, template_dir=str(tmp_path)))

    @app.route("/")
    def index():
        from chirp.templating.returns import Template

        return Template("index.html")

    return app


def test_macro_css_fires_for_dangling_class_without_chirpui(tmp_path) -> None:
    """A template emitting core-macro classes (chirp-dropdown) with chirp-ui not
    active -> macro_css WARNING. Proves check_macro_css is wired AND that the
    chirpui_components signal (absent here) reaches the rule as chirpui_active."""
    app = _macro_css_app(tmp_path, _MACRO_CSS_DANGLING)
    macro = [i for i in _issues(app) if i.category == "macro_css"]
    assert macro, "macro_css (#148) did not fire through check_hypermedia_surface"
    assert all(i.severity is Severity.WARNING for i in macro)
    assert any("chirp-dropdown" in i.message for i in macro)


def test_macro_css_silent_for_custom_classes(tmp_path) -> None:
    """Negative control: a template with no core-macro import and no dangling
    class -> no macro_css issue."""
    app = _macro_css_app(tmp_path, _MACRO_CSS_CLEAN)
    assert "macro_css" not in _categories(app)


# ---------------------------------------------------------------------------
# chirpui_css_verify (#157 child 2) -- unknown chirpui-* classes, chirp-ui on
# ---------------------------------------------------------------------------

_CHIRPUI_CSS_UNKNOWN = '<div class="chirpui-card chirpui-cardd-typo">x</div>'
_CHIRPUI_CSS_KNOWN = '<div class="chirpui-card">x</div>'


def _chirpui_css_verify_app(tmp_path, template_html: str) -> App:
    pytest.importorskip("chirp_ui")
    from chirp.ext.chirp_ui import use_chirp_ui

    (tmp_path / "index.html").write_text(template_html, encoding="utf-8")
    app = App(AppConfig(skip_contract_checks=True, template_dir=str(tmp_path)))
    use_chirp_ui(app)

    @app.route("/")
    def index():
        from chirp.templating.returns import Template

        return Template("index.html")

    return app


def test_chirpui_css_verify_fires_for_unknown_class_with_chirpui(tmp_path) -> None:
    """Unknown chirpui-* class with chirp-ui active -> chirpui_css_verify WARNING."""
    app = _chirpui_css_verify_app(tmp_path, _CHIRPUI_CSS_UNKNOWN)
    css_issues = [i for i in _issues(app) if i.category == "chirpui_css_verify"]
    assert css_issues, "chirpui_css_verify (#157) did not fire through check_hypermedia_surface"
    assert any("chirpui-cardd-typo" in i.message for i in css_issues)


def test_chirpui_css_verify_silent_for_known_class(tmp_path) -> None:
    """Negative control: a known chirpui-* class -> no chirpui_css_verify issue."""
    app = _chirpui_css_verify_app(tmp_path, _CHIRPUI_CSS_KNOWN)
    assert "chirpui_css_verify" not in _categories(app)


# ---------------------------------------------------------------------------
# htmx_provisioned (#185) -- hx-*/sse-* attrs with htmx not provisioned
# ---------------------------------------------------------------------------

# hx-get with no AppConfig(htmx=True) and no htmx <script> marker.
_HTMX_UNPROVISIONED = '<div id="x"><button hx-get="/data" hx-target="#x">Load</button></div>'
# Same template, but the layout ships an htmx <script> marker.
_HTMX_PROVISIONED_MARKER = (
    '<div id="x"><script data-chirp="htmx" src="/static/htmx.js"></script>'
    '<button hx-get="/data" hx-target="#x">Load</button></div>'
)


def _htmx_app(tmp_path, template_html: str, *, htmx_config: bool = False) -> App:
    (tmp_path / "index.html").write_text(template_html, encoding="utf-8")
    app = App(AppConfig(skip_contract_checks=True, template_dir=str(tmp_path), htmx=htmx_config))

    @app.route("/")
    def index():
        from chirp.templating.returns import Template

        return Template("index.html")

    return app


def test_htmx_provisioned_fires_when_not_provisioned(tmp_path) -> None:
    """A template emitting hx-* attributes with htmx neither config-enabled nor
    script-provisioned -> htmx_provisioned WARNING. Proves check_htmx_provisioned
    is wired AND that app.config.htmx (False here) reaches the rule."""
    app = _htmx_app(tmp_path, _HTMX_UNPROVISIONED)
    htmx = [i for i in _issues(app) if i.category == "htmx_provisioned"]
    assert htmx, "htmx_provisioned (#185) did not fire through check_hypermedia_surface"
    assert all(i.severity is Severity.WARNING for i in htmx)


def test_htmx_provisioned_silent_when_config_enabled(tmp_path) -> None:
    """Negative control: AppConfig(htmx=True) provisions htmx, so the same
    hx-*-bearing template stays silent. If this fired, the config flag would not
    be reaching the rule."""
    app = _htmx_app(tmp_path, _HTMX_UNPROVISIONED, htmx_config=True)
    assert "htmx_provisioned" not in _categories(app)


def test_htmx_provisioned_silent_when_script_marker_present(tmp_path) -> None:
    """Negative control: an htmx <script> marker in the template chain counts as
    provisioned -> the rule stays silent."""
    app = _htmx_app(tmp_path, _HTMX_PROVISIONED_MARKER)
    assert "htmx_provisioned" not in _categories(app)
