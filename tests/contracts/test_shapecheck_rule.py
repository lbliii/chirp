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

from chirp.contracts.rules_data_shapes import check_data_shapes
from chirp.contracts.rules_shapecheck import check_shapecheck
from chirp.contracts.types import Severity
from chirp.data import Composite, Shape, composite, get_db, shape
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
