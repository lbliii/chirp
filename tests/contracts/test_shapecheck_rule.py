"""Verified-Shape render contract (#166/#168/#173).

``shapecheck`` verifies the *render* side of ``@shape``-decorated row models:
block field reads must be Shape-provided (SELECT columns or declared
``computed=``), surface-contract registry names must resolve to a real Shape,
and a Shape column no block reads is a humble over-fetch WARNING. These are
direct-call unit tests mirroring ``test_data_shapes_rule.py``.

All Shape names are neutral public examples (Board / Card / Member); the
fixtures use a ``ShapeCheck`` prefix to stay unique in the process-wide registry.
"""

from dataclasses import dataclass
from types import SimpleNamespace

from kida import DictLoader, Environment

from chirp.contracts.rules_data_shapes import _parse_select_columns, check_data_shapes
from chirp.contracts.rules_shapecheck import check_shapecheck
from chirp.contracts.types import Severity
from chirp.data import Composite, Shape, composite, get_db, nested, shape
from chirp.templating.returns import Fragment


# Module-level so handler ``__globals__`` can resolve the Shape name. The Shape
# registry is module-global (one process-wide namespace), so these test fixtures
# use file-unique neutral names (``ShapeCheck*``) to avoid colliding with the L1
# ``test_shapes.py`` fixtures (``BoardView`` / ``BoardDetail``) -- a collision
# would fail-loud per the same-name policy (§8.7).
@shape("SELECT id, title, summary FROM boards WHERE id = :id")
@dataclass(frozen=True, slots=True)
class ShapeCheckBoardDetail:
    id: int
    title: str
    summary: str


@shape("SELECT id, title FROM boards WHERE id = :id", computed=("badge",))
@dataclass(frozen=True, slots=True)
class ShapeCheckBoardCard:
    id: int
    title: str


@shape("SELECT id, name FROM cards WHERE board_id = :board_id")
@dataclass(frozen=True, slots=True)
class ShapeCheckCard:
    id: int
    name: str


@shape("SELECT * FROM members")
@dataclass(frozen=True, slots=True)
class ShapeCheckMember:
    id: int
    name: str


# A Shape with a derived @property over its columns -- the idiomatic reason to
# use a dataclass over a tuple. ``full_name`` is NOT a SELECT column and is read
# directly in a template; it must never false-positive as an under-fetch, and the
# columns it consumes (first_name/last_name) must not noise as over-fetch.
@shape("SELECT id, first_name, last_name FROM people WHERE id = :id")
@dataclass(frozen=True, slots=True)
class ShapeCheckPerson:
    id: int
    first_name: str
    last_name: str

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}"


# A Shape with a derived *method* over a column (``url()`` over ``slug``).
@shape("SELECT id, slug FROM articles WHERE id = :id")
@dataclass(frozen=True, slots=True)
class ShapeCheckArticle:
    id: int
    slug: str

    def url(self) -> str:
        return f"/articles/{self.slug}"


def _env(template: str, name: str = "board.html") -> Environment:
    return Environment(loader=DictLoader({name: template}))


def _snapshot(env, handler, *, path="/boards", extras=None):
    route = SimpleNamespace(handler=handler, page_source_handler=None, path=path)
    router = SimpleNamespace(routes=[route])
    template_name = "board.html"
    return SimpleNamespace(
        kida_env=env,
        router=router,
        route_templates={path: template_name},
        extras=extras if extras is not None else {},
    )


def _of(issues, severity):
    return [i for i in issues if i.severity is severity]


# ---------------------------------------------------------------------------
# Under-fetch (#173) — block reads a field the Shape neither fetched nor declared
# ---------------------------------------------------------------------------


def test_underfetch_errors() -> None:
    env = _env(
        "{% block detail %}<h1>{{ board.title }}</h1><p>{{ board.author }}</p>{% endblock %}"
    )

    def handler():
        db = get_db()
        board = Shape.fetch(ShapeCheckBoardCard, db, id=1)
        return Fragment("board.html", "detail", board=board)

    issues = check_shapecheck(_snapshot(env, handler))
    errors = _of(issues, Severity.ERROR)
    assert len(errors) == 1
    assert errors[0].category == "shapecheck"
    assert "board.author" in errors[0].message
    assert "ShapeCheckBoardCard" in errors[0].message
    # An ERROR fired -> no PASS line.
    assert not _of(issues, Severity.INFO)


# ---------------------------------------------------------------------------
# Declared computed (#168) — a declared computed member satisfies the read
# ---------------------------------------------------------------------------


def test_declared_computed_satisfied() -> None:
    env = _env(
        "{% block detail %}<h1>{{ board.title }}</h1>"
        "<span>{{ board.badge }}</span><p>{{ board.id }}</p>{% endblock %}"
    )

    def handler():
        db = get_db()
        board = Shape.fetch(ShapeCheckBoardCard, db, id=1)
        return Fragment("board.html", "detail", board=board)

    issues = check_shapecheck(_snapshot(env, handler))
    # ``badge`` is declared computed -> no under-fetch ERROR.
    assert not _of(issues, Severity.ERROR)
    # All columns read -> no over-fetch. Clean -> a PASS line.
    assert _of(issues, Severity.INFO)


def test_undeclared_computed_errors() -> None:
    # ``badge`` is NOT declared on this Shape, so reading it is an under-fetch.
    env = _env(
        "{% block detail %}<h1>{{ board.title }}</h1><span>{{ board.badge }}</span>{% endblock %}"
    )

    def handler():
        db = get_db()
        board = Shape.fetch(ShapeCheckBoardDetail, db, id=1)
        return Fragment("board.html", "detail", board=board)

    errors = _of(check_shapecheck(_snapshot(env, handler)), Severity.ERROR)
    assert len(errors) == 1
    assert "board.badge" in errors[0].message


# ---------------------------------------------------------------------------
# Registry drift (#166) — THE HEADLINE
# ---------------------------------------------------------------------------


def test_registry_drift_errors_with_suggestion() -> None:
    # A surface contract names a Shape that does not exist; difflib suggests the
    # closest registered name. Uses this file's own ``ShapeCheckBoardDetail`` so
    # the suggestion is deterministic regardless of cross-file import order.
    snap = SimpleNamespace(
        kida_env=None,
        router=SimpleNamespace(routes=[]),
        route_templates={},
        extras={"surface_contracts": {"board-page": "ShapeCheckBoardDetial"}},  # typo
    )
    errors = _of(check_shapecheck(snap), Severity.ERROR)
    assert len(errors) == 1
    assert errors[0].category == "shapecheck"
    assert "ShapeCheckBoardDetial" in errors[0].message
    assert "ShapeCheckBoardDetail" in (errors[0].details or "")  # the suggestion


def test_registry_drift_silent_for_known_shape() -> None:
    snap = SimpleNamespace(
        kida_env=None,
        router=SimpleNamespace(routes=[]),
        route_templates={},
        extras={"surface_contracts": {"board-page": "ShapeCheckBoardDetail"}},  # exists
    )
    assert check_shapecheck(snap) == []


def test_registry_drift_runs_with_no_extras_set() -> None:
    # §8.5 #1: never subscript extras. With NO extras at all the rule must still
    # run (and find drift when present). Here, no drift but the call must not
    # raise / silently disable -- extras.get(...) returns {} and the auto
    # registry is consulted.
    env = _env("{% block detail %}<h1>{{ board.title }}</h1>{% endblock %}")

    def handler():
        db = get_db()
        board = Shape.fetch(ShapeCheckBoardCard, db, id=1)
        return Fragment("board.html", "detail", board=board)

    snap = _snapshot(env, handler, extras={})  # explicitly empty extras
    issues = check_shapecheck(snap)
    # No surface_contracts -> no drift error; the field check still ran.
    assert not _of(issues, Severity.ERROR)


def test_registry_drift_found_via_auto_registry_no_extras() -> None:
    # A drifting surface name supplied, but otherwise no opt-in: the auto
    # shape_registry() is the source of truth, not an injected registry.
    snap = SimpleNamespace(
        kida_env=None,
        router=SimpleNamespace(routes=[]),
        route_templates={},
        extras={"surface_contracts": {"x": "TotallyMissingShape"}},
    )
    errors = _of(check_shapecheck(snap), Severity.ERROR)
    assert len(errors) == 1
    assert "TotallyMissingShape" in errors[0].message


# ---------------------------------------------------------------------------
# Escape hatches — no false positives
# ---------------------------------------------------------------------------


def test_loop_collapse_no_false_positive() -> None:
    # A list pattern: depends_on collapses to the collection root ``cards`` with
    # no ``cards.field``; the per-item field reads are invisible -> no claim.
    env = _env(
        "{% block list %}{% for c in cards %}<li>{{ c.ghost }}</li>{% endfor %}{% endblock %}"
    )

    def handler():
        db = get_db()
        cards = Shape.fetch(ShapeCheckCard, db, board_id=1)
        return Fragment("board.html", "list", cards=cards)

    issues = check_shapecheck(_snapshot(env, handler))
    # ``cards`` root is provided (verified); the loop body ``c.ghost`` is invisible.
    assert not _of(issues, Severity.ERROR)


def test_url_for_global_no_false_positive() -> None:
    env = _env(
        "{% block detail %}<h1>{{ board.title }}</h1>"
        "<a href=\"{{ url_for('home') }}\">home</a>"
        "<p>{{ board.id }}</p>{% endblock %}"
    )

    def handler():
        db = get_db()
        board = Shape.fetch(ShapeCheckBoardCard, db, id=1)
        return Fragment("board.html", "detail", board=board)

    issues = check_shapecheck(_snapshot(env, handler))
    # ``url_for`` leaks into depends_on but is a global -> subtracted.
    assert not _of(issues, Severity.ERROR)


def test_set_local_no_false_positive() -> None:
    env = _env(
        "{% block detail %}{% set total = board.title %}"
        "<p>{{ total }}</p><p>{{ board.id }}</p>{% endblock %}"
    )

    def handler():
        db = get_db()
        board = Shape.fetch(ShapeCheckBoardCard, db, id=1)
        return Fragment("board.html", "detail", board=board)

    issues = check_shapecheck(_snapshot(env, handler))
    # ``total`` is a block-local {% set %} binding -> subtracted, not a field.
    assert not _of(issues, Severity.ERROR)


def test_dataclass_property_no_false_positive() -> None:
    # The dominant adversarial case: a @shape-decorated frozen dataclass with a
    # derived @property read directly in a template. ``full_name`` is NOT a
    # SELECT column -- but it is a real attribute that resolves at runtime, so it
    # must NOT fire an under-fetch ERROR, and the columns it consumes inside its
    # body (first_name/last_name, invisible to depends_on) must NOT noise as
    # over-fetch.
    env = _env("{% block detail %}<h1>{{ person.full_name }}</h1>{% endblock %}")

    def handler():
        db = get_db()
        person = Shape.fetch(ShapeCheckPerson, db, id=1)
        return Fragment("board.html", "detail", person=person)

    issues = check_shapecheck(_snapshot(env, handler))
    assert not _of(issues, Severity.ERROR), [i.message for i in _of(issues, Severity.ERROR)]
    # No spurious over-fetch on the property-consumed columns either.
    assert not _of(issues, Severity.WARNING), [i.message for i in _of(issues, Severity.WARNING)]
    # Clean binding -> a PASS line.
    assert _of(issues, Severity.INFO)


def test_dataclass_method_no_false_positive() -> None:
    # A derived *method* read on the bound shape var (``article.url()`` over the
    # ``slug`` column). kida emits depends_on=['article.url']; ``url`` is a real
    # method, not a column typo -> no under-fetch ERROR, no over-fetch noise.
    env = _env('{% block detail %}<a href="{{ article.url() }}">read</a>{% endblock %}')

    def handler():
        db = get_db()
        article = Shape.fetch(ShapeCheckArticle, db, id=1)
        return Fragment("board.html", "detail", article=article)

    issues = check_shapecheck(_snapshot(env, handler))
    assert not _of(issues, Severity.ERROR), [i.message for i in _of(issues, Severity.ERROR)]
    assert not _of(issues, Severity.WARNING), [i.message for i in _of(issues, Severity.WARNING)]
    assert _of(issues, Severity.INFO)


def test_field_method_on_column_value_is_fine() -> None:
    # ``board.title.upper()`` -- a str method on a *column value*, not a derived
    # accessor on the shape var. Only the first attr (``title``, a real column)
    # is checked; the ``.upper`` segment is never claimed. ``title`` counts as
    # read, so it is NOT over-fetch noise (contrast the genuine-typo path).
    env = _env(
        "{% block detail %}<h1>{{ board.title.upper() }}</h1><p>{{ board.id }}</p>{% endblock %}"
    )

    def handler():
        db = get_db()
        board = Shape.fetch(ShapeCheckBoardCard, db, id=1)
        return Fragment("board.html", "detail", board=board)

    issues = check_shapecheck(_snapshot(env, handler))
    assert not _of(issues, Severity.ERROR)
    # Both columns (id, title) read -> no over-fetch.
    assert not _of(issues, Severity.WARNING)
    assert _of(issues, Severity.INFO)


def test_genuine_typo_still_errors_alongside_accessors() -> None:
    # Guardrail: the accessor escape hatch must NOT swallow a real column typo on
    # a Shape that also has a derived accessor. ``ghost`` is neither a column nor
    # an accessor -> still an ERROR, even though ``full_name`` is read too.
    env = _env(
        "{% block detail %}<h1>{{ person.full_name }}</h1><p>{{ person.ghost }}</p>{% endblock %}"
    )

    def handler():
        db = get_db()
        person = Shape.fetch(ShapeCheckPerson, db, id=1)
        return Fragment("board.html", "detail", person=person)

    errors = _of(check_shapecheck(_snapshot(env, handler)), Severity.ERROR)
    assert len(errors) == 1
    assert "person.ghost" in errors[0].message
    assert "full_name" not in errors[0].message


def test_deep_dotted_only_checks_first_attr() -> None:
    # §8.6: ``board.meta.created`` and ``board.tags['x']`` -> only ``meta`` /
    # ``tags`` are checked, never ``created`` / ``x``. ``meta`` and ``tags`` are
    # NOT Shape columns, so each fires once; ``created``/``x`` never do.
    env = _env(
        "{% block detail %}<p>{{ board.meta.created }}</p>"
        "<p>{{ board.tags['x'] }}</p>{% endblock %}"
    )

    def handler():
        db = get_db()
        board = Shape.fetch(ShapeCheckBoardCard, db, id=1)
        return Fragment("board.html", "detail", board=board)

    errors = _of(check_shapecheck(_snapshot(env, handler)), Severity.ERROR)
    messages = " ".join(e.message for e in errors)
    assert "board.meta" in messages
    assert "board.tags" in messages
    # The deeper segments are NEVER flagged.
    assert ".created" not in messages
    assert ".x" not in messages


def test_opaque_shape_skipped() -> None:
    # ``SELECT *`` -> columns == () -> opaque -> escape hatch (no field claims).
    env = _env("{% block detail %}<p>{{ member.anything_at_all }}</p>{% endblock %}")

    def handler():
        db = get_db()
        member = Shape.fetch(ShapeCheckMember, db)
        return Fragment("board.html", "detail", member=member)

    issues = check_shapecheck(_snapshot(env, handler))
    assert not _of(issues, Severity.ERROR)
    assert not _of(issues, Severity.WARNING)


def test_kida_env_none_is_noop_for_field_checks() -> None:
    # With kida_env=None there is no template metadata; only registry drift can
    # run. No surface_contracts here -> nothing at all.
    def handler():
        db = get_db()
        board = Shape.fetch(ShapeCheckBoardCard, db, id=1)
        return Fragment("board.html", "detail", board=board)

    snap = SimpleNamespace(
        kida_env=None,
        router=SimpleNamespace(
            routes=[SimpleNamespace(handler=handler, page_source_handler=None, path="/b")]
        ),
        route_templates={"/b": "board.html"},
        extras={},
    )
    assert check_shapecheck(snap) == []


# ---------------------------------------------------------------------------
# Over-fetch (#166) — a provided column no block reads -> WARNING (default)
# ---------------------------------------------------------------------------


def test_overfetch_warns() -> None:
    # ``summary`` is fetched but never read by the block -> over-fetch WARNING.
    env = _env("{% block detail %}<h1>{{ board.title }}</h1><p>{{ board.id }}</p>{% endblock %}")

    def handler():
        db = get_db()
        board = Shape.fetch(ShapeCheckBoardDetail, db, id=1)
        return Fragment("board.html", "detail", board=board)

    issues = check_shapecheck(_snapshot(env, handler))
    warnings = _of(issues, Severity.WARNING)
    assert any("summary" in w.message for w in warnings)
    assert not _of(issues, Severity.ERROR)


# ---------------------------------------------------------------------------
# Ownership boundary (§8.4) — ``data`` does not fire on Shape.fetch
# ---------------------------------------------------------------------------


def test_data_category_does_not_fire_on_shape_fetch() -> None:
    # ``Shape.fetch(...)`` receiver is the Shape class, not a db handle, so
    # _is_db_receiver rejects it -> the ``data`` rule never fires on it. This is
    # the non-collision-by-construction guarantee from §8.4.
    def handler():
        db = get_db()
        # A genuinely drifting SELECT (``ghost`` is no field), but on Shape.fetch.
        return Shape.fetch(ShapeCheckBoardCard, db, id=1)

    route = SimpleNamespace(handler=handler, page_source_handler=None, path="/b")
    router = SimpleNamespace(routes=[route])
    assert check_data_shapes(router, None) == []


# ---------------------------------------------------------------------------
# Explicit binding escape hatch (§8.5 #2)
# ---------------------------------------------------------------------------


def test_explicit_binding_verifies_root() -> None:
    # When static binding can't resolve, shapecheck_bindings provides it. The
    # explicit form (no var name) root-verifies the binding (PASS line) without
    # field claims.
    env = _env("{% block detail %}<h1>{{ board.title }}</h1>{% endblock %}")

    snap = SimpleNamespace(
        kida_env=env,
        router=SimpleNamespace(routes=[]),
        route_templates={},
        extras={"shapecheck_bindings": {("board.html", "detail"): "ShapeCheckBoardDetail"}},
    )
    issues = check_shapecheck(snap)
    assert not _of(issues, Severity.ERROR)
    assert _of(issues, Severity.INFO)  # PASS line for the verified binding


# ---------------------------------------------------------------------------
# Un-analyzable route source (#12) — INFO, not a silent binding drop
# ---------------------------------------------------------------------------


def test_unanalyzable_route_source_emits_info() -> None:
    # #12 (B2 round-2): a handler whose ``inspect.getsource`` fails (here an
    # exec-compiled function with no on-disk source -> OSError) cannot have its
    # Shape render bindings statically recovered. Rather than SILENTLY dropping
    # every binding for the route with no diagnostic, shapecheck must surface an
    # INFO so a developer wondering why a route is unverified sees it was skipped.
    env = _env("{% block detail %}<h1>{{ board.title }}</h1>{% endblock %}")

    ns: dict = {}
    # An exec-compiled handler: real callable, but inspect.getsource raises
    # OSError ("could not get source code") -> the #12 INFO branch. The exec is
    # the *mechanism under test* (a handler with no on-disk source), not a
    # production pattern -> intentional S102.
    exec("def dynamic_handler():\n    return None", ns)  # noqa: S102
    handler = ns["dynamic_handler"]

    snap = _snapshot(env, handler, path="/dynamic")
    issues = check_shapecheck(snap)
    info = _of(issues, Severity.INFO)
    skipped = [i for i in info if "shapecheck skipped route" in i.message]
    assert len(skipped) == 1, [i.message for i in info]
    assert skipped[0].category == "shapecheck"
    assert "/dynamic" in skipped[0].message
    assert "dynamic_handler" in skipped[0].message
    # The skip is a diagnostic, not an error/warning.
    assert not _of(issues, Severity.ERROR)
    assert not _of(issues, Severity.WARNING)


# ---------------------------------------------------------------------------
# Tenant scope (#169, §8.1) — the ONE statically-decidable scope ERROR
# ---------------------------------------------------------------------------


# A scoped Shape whose SQL is opaque/un-injectable (SELECT *): the compiler
# CANNOT inject the scope predicate -> the single statically-decidable scope
# ERROR. Registered at import so it is visible to the auto shape_registry().
@shape("SELECT * FROM secrets WHERE id = :id", scope="community_id")
@dataclass(frozen=True, slots=True)
class ShapeCheckOpaqueScoped:
    id: int


# A scoped Shape with an injectable SQL: must NOT fire (the compiler injects).
@shape("SELECT id, title FROM scoped_things WHERE id = :id", scope="community_id")
@dataclass(frozen=True, slots=True)
class ShapeCheckInjectableScoped:
    id: int
    title: str


def test_opaque_scoped_shape_errors() -> None:
    # §8.1 #3: scope= declared but SQL opaque/un-injectable -> shapecheck ERROR.
    # The Shape is "used" by this app via a (clean) surface contract; the scope
    # check runs over the app's used Shapes, not the whole process-wide registry.
    snap = SimpleNamespace(
        kida_env=None,
        router=SimpleNamespace(routes=[]),
        route_templates={},
        extras={"surface_contracts": {"secrets": "ShapeCheckOpaqueScoped"}},
    )
    errors = _of(check_shapecheck(snap), Severity.ERROR)
    opaque = [e for e in errors if "ShapeCheckOpaqueScoped" in e.message]
    assert len(opaque) == 1
    assert opaque[0].category == "shapecheck"
    assert "community_id" in opaque[0].message
    assert "opaque" in opaque[0].message.lower() or "un-injectable" in opaque[0].message.lower()


def test_injectable_scoped_shape_does_not_error() -> None:
    # The negative control: an injectable scoped Shape (simple SELECT with an
    # analyzable FROM) is silently OK -- the compiler injects the predicate.
    snap = SimpleNamespace(
        kida_env=None,
        router=SimpleNamespace(routes=[]),
        route_templates={},
        extras={"surface_contracts": {"things": "ShapeCheckInjectableScoped"}},
    )
    errors = _of(check_shapecheck(snap), Severity.ERROR)
    assert not [e for e in errors if "ShapeCheckInjectableScoped" in e.message]


# ---------------------------------------------------------------------------
# Comment-aware projection parsing (R3-5) — a comment in the SELECT list is not
# opaque, so a scoped Shape carrying one must NOT be false-rejected.
# ---------------------------------------------------------------------------


# A scoped Shape with an inline block comment AND a line comment in the
# projection. Before the fix _parse_select_columns returned None (the comment
# defeated the regex), the SQL looked opaque, and the scope-injectability check
# false-rejected it with a misleading "CTE / UNION / SELECT * / derived-table"
# message. The columns are perfectly analyzable once comments are stripped.
@shape(
    "SELECT id /* the row id */, title -- the display title\nFROM "
    "shapecheck_commented WHERE id = :id",
    scope="community_id",
)
@dataclass(frozen=True, slots=True)
class ShapeCheckCommentedScoped:
    id: int
    title: str


def test_parse_select_columns_is_comment_aware() -> None:
    # R3-5: inline block + line comments in the projection no longer make the
    # SELECT opaque -- the analyzable column list is recovered.
    assert _parse_select_columns("SELECT id /* note */, name FROM t WHERE id = :id") == (
        "id",
        "name",
    )
    assert _parse_select_columns("SELECT id, -- trailing\nname FROM t") == ("id", "name")
    # A comment that hides part of a column name is stripped to a space, so
    # adjacent tokens never merge into a bogus identifier.
    assert _parse_select_columns("SELECT a /**/ , b FROM t") == ("a", "b")
    # String-literal aware: a ``/*`` inside a ``'...'`` literal is NOT a comment,
    # so it does not swallow the rest of the SQL -- the trailing alias and FROM
    # are still recovered (the literal column is non-analyzable, but the aliased
    # one resolves to its output name).
    assert _parse_select_columns("SELECT 'a /* b' AS note, id FROM t") == ("note", "id")


def test_commented_scoped_shape_is_injectable_not_false_rejected() -> None:
    # R3-5: a scoped Shape whose projection carries comments parses cleanly and is
    # injectable -> NO scope ERROR (it would have been a misleading false-reject
    # before the comment-aware parse).
    snap = SimpleNamespace(
        kida_env=None,
        router=SimpleNamespace(routes=[]),
        route_templates={},
        extras={"surface_contracts": {"commented": "ShapeCheckCommentedScoped"}},
    )
    errors = _of(check_shapecheck(snap), Severity.ERROR)
    assert not [e for e in errors if "ShapeCheckCommentedScoped" in e.message], [
        e.message for e in errors if "ShapeCheckCommentedScoped" in e.message
    ]


# ---------------------------------------------------------------------------
# Page-composite (#170) — per-block subset check resolves the composite field
# ---------------------------------------------------------------------------


@shape("SELECT id, title FROM cc_boards WHERE id = :board_id")
@dataclass(frozen=True, slots=True)
class ShapeCheckCompBoard:
    id: int
    title: str


@shape("SELECT id, name FROM cc_members WHERE board_id = :board_id")
@dataclass(frozen=True, slots=True)
class ShapeCheckCompMember:
    id: int
    name: str


@composite()
@dataclass(frozen=True, slots=True)
class ShapeCheckCompPage:
    board: ShapeCheckCompBoard
    members: tuple[ShapeCheckCompMember, ...]


def test_composite_field_provides_block_subset() -> None:
    # A block bound to ``page.board`` reads ``board.title`` (a composite member
    # column) -> clean; reading ``board.ghost`` (not a member column) is an
    # under-fetch ERROR. The provided fields are resolved from the composite
    # member Shape, never via one query per block (§4-L4).
    env = _env("{% block detail %}<h1>{{ board.title }}</h1><p>{{ board.ghost }}</p>{% endblock %}")

    def handler():
        db = get_db()
        page = Composite.load(ShapeCheckCompPage, db, board_id=1)
        return Fragment("board.html", "detail", board=page.board)

    errors = _of(check_shapecheck(_snapshot(env, handler)), Severity.ERROR)
    assert len(errors) == 1
    assert errors[0].category == "shapecheck"
    assert "board.ghost" in errors[0].message
    assert "ShapeCheckCompBoard" in errors[0].message


def test_composite_field_clean_read_passes() -> None:
    # Reading only composite-member columns is clean -> a PASS line, no ERROR.
    env = _env("{% block detail %}<h1>{{ board.title }}</h1><p>{{ board.id }}</p>{% endblock %}")

    def handler():
        db = get_db()
        page = Composite.load(ShapeCheckCompPage, db, board_id=1)
        return Fragment("board.html", "detail", board=page.board)

    issues = check_shapecheck(_snapshot(env, handler))
    assert not _of(issues, Severity.ERROR)
    assert _of(issues, Severity.INFO)


def test_composite_unknown_field_is_skipped() -> None:
    # ``page.nope`` is not a composite member -> the kwarg resolves to no Shape,
    # so the binding is simply not collected (skip-not-guess, no false positive).
    env = _env("{% block detail %}<p>{{ data.whatever }}</p>{% endblock %}")

    def handler():
        db = get_db()
        page = Composite.load(ShapeCheckCompPage, db, board_id=1)
        return Fragment("board.html", "detail", data=page.nope)

    issues = check_shapecheck(_snapshot(env, handler))
    assert not _of(issues, Severity.ERROR)


# ---------------------------------------------------------------------------
# Nested-field render (#1) — the framework's headline nested() feature
# ---------------------------------------------------------------------------


# A child Shape and a parent Shape that declares a ``nested()`` field. ``cards``
# is a REAL dataclass field (the bounded compiler fills it) but NOT a SELECT
# column -- so a ``{% for c in board.cards %}`` read of the collection root must
# never false-fire under-fetch. Neutral ``ShapeCheck`` prefix for registry
# uniqueness (§8.7).
@shape("SELECT id, name, board_id FROM shapecheck_cards WHERE board_id = :board_id")
@dataclass(frozen=True, slots=True)
class ShapeCheckNestedCard:
    id: int
    name: str
    board_id: int


@shape("SELECT id, title FROM shapecheck_nest_boards WHERE id = :id")
@dataclass(frozen=True, slots=True)
class ShapeCheckNestedBoard:
    id: int
    title: str
    cards: tuple[ShapeCheckNestedCard, ...] = nested(ShapeCheckNestedCard, on="board_id", key="id")


def test_nested_field_read_is_not_underfetch() -> None:
    # #1: ``board.cards`` is a ``nested()`` field (not a SELECT column). Reading
    # the collection root must be clean -- before the fix this false-fired an
    # under-fetch ERROR on the framework's own marquee nested() feature. The
    # per-item ``c.name`` reads collapse to the loop root and stay invisible.
    env = _env(
        "{% block detail %}<h1>{{ board.title }}</h1>"
        "<ul>{% for c in board.cards %}<li>{{ c.name }}</li>{% endfor %}</ul>"
        "<p>{{ board.id }}</p>{% endblock %}"
    )

    def handler():
        db = get_db()
        board = Shape.fetch(ShapeCheckNestedBoard, db, id=1)
        return Fragment("board.html", "detail", board=board)

    issues = check_shapecheck(_snapshot(env, handler))
    assert not _of(issues, Severity.ERROR), [i.message for i in _of(issues, Severity.ERROR)]
    # ``cards`` is a nested field, not a column, so it must NOT count as an
    # over-fetch column either; both scalar columns (id, title) are read.
    assert not _of(issues, Severity.WARNING), [i.message for i in _of(issues, Severity.WARNING)]
    assert _of(issues, Severity.INFO)  # clean PASS


# ---------------------------------------------------------------------------
# Nested-block bleed (#2) — parent + nested child bound to DIFFERENT Shapes
# ---------------------------------------------------------------------------


@shape("SELECT id, title FROM shapecheck_bleed_boards WHERE id = :id")
@dataclass(frozen=True, slots=True)
class ShapeCheckBleedBoard:
    id: int
    title: str


@shape("SELECT id, body FROM shapecheck_bleed_comments WHERE card_id = :cid")
@dataclass(frozen=True, slots=True)
class ShapeCheckBleedComment:
    id: int
    body: str


def _multi_handler_snapshot(env, handler, *, path="/boards"):
    route = SimpleNamespace(handler=handler, page_source_handler=None, path=path)
    router = SimpleNamespace(routes=[route])
    return SimpleNamespace(
        kida_env=env,
        router=router,
        route_templates={path: "board.html"},
        extras={},
    )


def test_nested_block_bleed_no_false_positive_on_parent() -> None:
    # #2: the parent block reads ``board.title`` (valid). A nested child block --
    # nested under a ``{% for %}`` -- reads ``board.extra`` under the SAME var
    # name, where ``extra`` is NOT a parent column. kida's depends_on for the
    # parent is a conservative SUPERSET that absorbs the child's ``board.extra``;
    # without own-reads subtraction this false-fires an under-fetch ERROR on the
    # PARENT. The subtraction must remove the nested child's reads at any depth.
    env = _env(
        "{% block parent %}<h1>{{ board.title }}</h1>"
        "{% for x in board.title %}{% block child %}<span>{{ board.extra }}</span>"
        "{% endblock %}{% endfor %}{% endblock %}"
    )

    def handler():
        db = get_db()
        board = Shape.fetch(ShapeCheckBleedBoard, db, id=1)
        # Only the PARENT block is bound here.
        return Fragment("board.html", "parent", board=board)

    issues = check_shapecheck(_multi_handler_snapshot(env, handler))
    # No false under-fetch on the parent for the child's ``board.extra`` read.
    assert not _of(issues, Severity.ERROR), [i.message for i in _of(issues, Severity.ERROR)]


def test_nested_block_bleed_shared_read_fires_parent_underfetch() -> None:
    # #2 (B1 round-2): a dotted read (``board.owner``) that occurs in BOTH the
    # parent block body AND a nested child block under the SAME shapevar, where
    # ``owner`` is not a column. A naive set-difference own-reads (subtract the
    # child's depends_on from the parent's) would remove ``board.owner`` from the
    # parent ENTIRELY -- silently MISSING a genuine parent under-fetch (renders
    # None at runtime). Occurrence-granular own reads must RETAIN the parent's own
    # ``board.owner`` read so the under-fetch ERROR fires. Only the parent block
    # is bound; the only path to an ERROR is the retained shared read.
    env = _env(
        "{% block header %}<h1>{{ board.title }} by {{ board.owner }}</h1>"
        "{% if board.id %}{% block badge %}{{ board.owner }}{% endblock %}{% endif %}"
        "{% endblock %}"
    )

    def handler():
        db = get_db()
        board = Shape.fetch(ShapeCheckBleedBoard, db, id=1)
        # Only the PARENT (header) block is bound.
        return Fragment("board.html", "header", board=board)

    issues = check_shapecheck(_multi_handler_snapshot(env, handler))
    errors = _of(issues, Severity.ERROR)
    owner = [e for e in errors if "board.owner" in e.message]
    # The marquee assertion: the under-fetch FIRES (zero before the fix).
    assert len(owner) == 1, [e.message for e in errors]
    assert "ShapeCheckBleedBoard" in owner[0].message
    assert "owner" in owner[0].message
    # R3-6: the innermost OWNER of ``board.owner`` is the UNBOUND nested ``badge``
    # block, but attribution must name the BOUND binding whose contract was
    # actually verified (``header``) -- not a sibling/child block never bound to a
    # Shape. The read still fires; only the block NAME is the verified binding.
    assert "Block 'header'" in owner[0].message
    assert "Block 'badge'" not in owner[0].message
    # ``board.title`` and ``board.id`` are real columns -> no other under-fetch.
    assert not [e for e in errors if "board.title" in e.message]
    assert not [e for e in errors if "board.id" in e.message]


def test_nested_block_bleed_child_only_read_still_no_parent_false_positive() -> None:
    # B1 guardrail: the precise own-reads must keep the existing bleed property --
    # a read occurring ONLY inside a nested child (never in the parent body) must
    # NOT fire on the parent. ``board.extra`` lives solely in the nested child;
    # the parent reads only the real column ``board.title``. With only the parent
    # bound, no ERROR may fire (the child's read does not bleed up).
    env = _env(
        "{% block parent %}<h1>{{ board.title }}</h1>"
        "{% if board.title %}{% block child %}<span>{{ board.extra }}</span>"
        "{% endblock %}{% endif %}{% endblock %}"
    )

    def handler():
        db = get_db()
        board = Shape.fetch(ShapeCheckBleedBoard, db, id=1)
        return Fragment("board.html", "parent", board=board)

    issues = check_shapecheck(_multi_handler_snapshot(env, handler))
    assert not _of(issues, Severity.ERROR), [i.message for i in _of(issues, Severity.ERROR)]


def test_nested_block_bleed_attributes_to_correct_child_block() -> None:
    # #2 second half: when both parent and child are bound (to DIFFERENT Shapes),
    # the child's genuine under-fetch (``comment.bogus``) must be reported against
    # the block where the read SYNTACTICALLY lives (``child``), not the bound
    # ancestor (``parent``).
    env = _env(
        "{% block parent %}<h1>{{ board.title }}</h1>"
        "{% block child %}<span>{{ comment.bogus }}</span>{% endblock %}{% endblock %}"
    )

    def handler():
        db = get_db()
        board = Shape.fetch(ShapeCheckBleedBoard, db, id=1)
        comment = Shape.fetch(ShapeCheckBleedComment, db, cid=1)
        return [
            Fragment("board.html", "parent", board=board),
            Fragment("board.html", "child", comment=comment),
        ]

    issues = check_shapecheck(_multi_handler_snapshot(env, handler))
    errors = _of(issues, Severity.ERROR)
    # Exactly one under-fetch: ``comment.bogus`` -- attributed to ``child``.
    bogus = [e for e in errors if "comment.bogus" in e.message]
    assert len(bogus) == 1
    assert "Block 'child'" in bogus[0].message
    assert "Block 'parent'" not in bogus[0].message
    # The parent's ``board.title`` read is valid -> no parent under-fetch.
    assert not [e for e in errors if "board." in e.message]


# ---------------------------------------------------------------------------
# Column literally named 'form' / 'error' (#10) — still checkable
# ---------------------------------------------------------------------------


@shape("SELECT id, form FROM shapecheck_form_things WHERE id = :id")
@dataclass(frozen=True, slots=True)
class ShapeCheckHasFormColumn:
    id: int
    form: str


def test_column_named_form_is_still_checkable() -> None:
    # #10: noise/global/local subtraction must key off the context KEY (parts[0],
    # the shapevar root), not the ``.field`` attribute (parts[1]). A Shape column
    # literally named ``form`` is a real column -> reading ``board.form`` is
    # clean; reading ``board.error`` (not a column) is a genuine under-fetch. If
    # the rule keyed off the attribute, both would be silently suppressed.
    env = _env(
        "{% block detail %}<p>{{ board.form }}</p>"
        "<p>{{ board.error }}</p><p>{{ board.id }}</p>{% endblock %}"
    )

    def handler():
        db = get_db()
        board = Shape.fetch(ShapeCheckHasFormColumn, db, id=1)
        return Fragment("board.html", "detail", board=board)

    errors = _of(check_shapecheck(_multi_handler_snapshot(env, handler)), Severity.ERROR)
    # ``form`` is a real column -> not flagged; ``error`` is the only under-fetch.
    assert len(errors) == 1
    assert "board.error" in errors[0].message
    assert "board.form" not in errors[0].message


# ---------------------------------------------------------------------------
# Conditional default(none) hint (#11)
# ---------------------------------------------------------------------------


def test_default_none_hint_only_when_guard_present() -> None:
    # #11: the remediation hint "then delete the '| default(none)' guard" must
    # appear only when the flagged read actually carries that guard.
    guarded = _env(
        "{% block detail %}<p>{{ board.author | default(none) }}</p>"
        "<p>{{ board.id }}</p><p>{{ board.title }}</p>{% endblock %}"
    )
    unguarded = _env(
        "{% block detail %}<p>{{ board.author }}</p>"
        "<p>{{ board.id }}</p><p>{{ board.title }}</p>{% endblock %}"
    )

    def handler():
        db = get_db()
        board = Shape.fetch(ShapeCheckBoardCard, db, id=1)
        return Fragment("board.html", "detail", board=board)

    g_errors = _of(check_shapecheck(_multi_handler_snapshot(guarded, handler)), Severity.ERROR)
    u_errors = _of(check_shapecheck(_multi_handler_snapshot(unguarded, handler)), Severity.ERROR)
    assert len(g_errors) == 1
    assert len(u_errors) == 1
    assert "default(none)" in (g_errors[0].details or "")
    assert "default(none)" not in (u_errors[0].details or "")


# ---------------------------------------------------------------------------
# Over-fetch multi-binding dedup (#13)
# ---------------------------------------------------------------------------


def test_overfetch_dedups_across_repeated_bindings() -> None:
    # The same (template, block, shapevar, column) over-fetch must be reported
    # at most once even when the same binding is collected twice (e.g. two
    # returns to the same block). ``summary`` is fetched but never read.
    env = _env("{% block detail %}<h1>{{ board.title }}</h1><p>{{ board.id }}</p>{% endblock %}")

    def handler():
        db = get_db()
        board = Shape.fetch(ShapeCheckBoardDetail, db, id=1)
        if board:
            return Fragment("board.html", "detail", board=board)
        return Fragment("board.html", "detail", board=board)

    issues = check_shapecheck(_multi_handler_snapshot(env, handler))
    overfetch = [w for w in _of(issues, Severity.WARNING) if "summary" in w.message]
    # Two identical bindings collected, but the over-fetch fires exactly once.
    assert len(overfetch) == 1
    assert not _of(issues, Severity.ERROR)


# ---------------------------------------------------------------------------
# Under-fetch dedup carries the bound-shape identity (F6)
# ---------------------------------------------------------------------------


@shape("SELECT id, title FROM f6_alpha WHERE id = :id")
@dataclass(frozen=True, slots=True)
class ShapeCheckDedupAlpha:
    id: int
    title: str


@shape("SELECT id, body FROM f6_beta WHERE cid = :cid")
@dataclass(frozen=True, slots=True)
class ShapeCheckDedupBeta:
    id: int
    body: str


def test_underfetch_dedup_distinguishes_bound_shapes() -> None:
    # F6: a bound PARENT (ShapeCheckDedupAlpha) and a bound nested CHILD
    # (ShapeCheckDedupBeta) share the var name ``item`` and each reads ``item.x``
    # -- a field neither Shape provides. R3-6 re-attributes both reads to the
    # innermost BOUND owner (the nested ``child`` block), so before the fix the
    # dedup key (template, block, var, field) collided and ONE of the two real
    # under-fetches was silently dropped (and even mislabeled with the wrong
    # Shape). Including the resolved Shape NAME in the dedup key reports both
    # distinct (shape, var, field) under-fetches separately.
    env = _env(
        "{% block parent %}<h1>{{ item.title }}</h1><p>{{ item.x }}</p>"
        "{% block child %}<span>{{ item.body }}</span><p>{{ item.x }}</p>"
        "{% endblock %}{% endblock %}"
    )

    def handler():
        db = get_db()
        alpha = Shape.fetch(ShapeCheckDedupAlpha, db, id=1)
        beta = Shape.fetch(ShapeCheckDedupBeta, db, cid=1)
        return [
            Fragment("board.html", "parent", item=alpha),
            Fragment("board.html", "child", item=beta),
        ]

    errors = _of(check_shapecheck(_multi_handler_snapshot(env, handler)), Severity.ERROR)
    item_x = [e for e in errors if "item.x" in e.message]
    # TWO distinct under-fetch ERRORs -- one per bound Shape -- not one.
    assert len(item_x) == 2, [e.message for e in item_x]
    shapes_named = {
        s for s in ("ShapeCheckDedupAlpha", "ShapeCheckDedupBeta") for e in item_x if s in e.message
    }
    assert shapes_named == {"ShapeCheckDedupAlpha", "ShapeCheckDedupBeta"}, [
        e.message for e in item_x
    ]


def test_underfetch_dedup_collapses_genuine_duplicate() -> None:
    # Guardrail for F6: the SAME (shape, var, field) under-fetch collected twice
    # (e.g. two returns to the same bound block on the same Shape) is still
    # reported exactly once -- the shape-identity key de-dups genuine duplicates,
    # it only stops collapsing GENUINELY DISTINCT shapes.
    env = _env("{% block detail %}<p>{{ board.ghost }}</p><h1>{{ board.title }}</h1>{% endblock %}")

    def handler():
        db = get_db()
        board = Shape.fetch(ShapeCheckBoardCard, db, id=1)
        if board:
            return Fragment("board.html", "detail", board=board)
        return Fragment("board.html", "detail", board=board)

    errors = _of(check_shapecheck(_multi_handler_snapshot(env, handler)), Severity.ERROR)
    ghost = [e for e in errors if "board.ghost" in e.message]
    assert len(ghost) == 1, [e.message for e in ghost]


# ---------------------------------------------------------------------------
# Over-fetch is computed against the shape-group read UNION (F7)
# ---------------------------------------------------------------------------


@shape("SELECT id, title, sidebar FROM f7_boards WHERE id = :id")
@dataclass(frozen=True, slots=True)
class ShapeCheckF7Board:
    id: int
    title: str
    sidebar: str


def test_overfetch_not_fired_when_nested_child_of_same_shape_reads_column() -> None:
    # F7: R3/round-2 switched over-fetch's read set to occurrence-granular OWN
    # reads. A column the PARENT block SELECTs that is read ONLY by a nested CHILD
    # block bound to the SAME shape (``sidebar``, read in ``child``) would
    # false-fire an over-fetch WARNING on the parent under own-reads. The column
    # IS consumed by a binding of the shape, so over-fetch must be computed
    # against the UNION of reads across all bound blocks of the shape: no WARNING
    # on either block.
    env = _env(
        "{% block parent %}<h1>{{ board.title }}</h1><p>{{ board.id }}</p>"
        "{% block child %}<aside>{{ board.sidebar }}</aside>{% endblock %}{% endblock %}"
    )

    def handler():
        db = get_db()
        board = Shape.fetch(ShapeCheckF7Board, db, id=1)
        return [
            Fragment("board.html", "parent", board=board),
            Fragment("board.html", "child", board=board),
        ]

    issues = check_shapecheck(_multi_handler_snapshot(env, handler))
    # ``sidebar`` is read by the child; ``id``/``title`` by the parent -> the
    # union covers every column -> no over-fetch on either block.
    assert not _of(issues, Severity.WARNING), [w.message for w in _of(issues, Severity.WARNING)]
    assert not _of(issues, Severity.ERROR), [e.message for e in _of(issues, Severity.ERROR)]


def test_overfetch_still_fires_when_no_binding_reads_the_column() -> None:
    # Guardrail for F7: the union must NOT mask a genuinely unread column. Here
    # ``sidebar`` is read by NO binding of the shape -> it is truly over-fetch and
    # the WARNING must still fire (the union only excuses a column some binding
    # consumes).
    env = _env(
        "{% block parent %}<h1>{{ board.title }}</h1><p>{{ board.id }}</p>"
        "{% block child %}<span>read nothing extra</span>{% endblock %}{% endblock %}"
    )

    def handler():
        db = get_db()
        board = Shape.fetch(ShapeCheckF7Board, db, id=1)
        return [
            Fragment("board.html", "parent", board=board),
            Fragment("board.html", "child", board=board),
        ]

    issues = check_shapecheck(_multi_handler_snapshot(env, handler))
    overfetch = [w for w in _of(issues, Severity.WARNING) if "sidebar" in w.message]
    assert overfetch, [w.message for w in _of(issues, Severity.WARNING)]
