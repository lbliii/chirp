"""Tests for the Shapes workspaces example — the three things Shapes give you.

1. A verified SQL->render contract: ``shapecheck`` is clean on the shipped app
   and fails loud on drift.
2. Tenant isolation you cannot forget (``scope=``): proven at the page layer
   *and* directly at the data layer.
3. No N+1: the dashboard loads in a bounded query count, independent of how many
   rows it returns.
"""

from chirp.contracts import check_hypermedia_surface
from chirp.data import Composite, Shape
from chirp.testing import TestClient


class _CountingDB:
    """Forward everything to a real Database, counting ``fetch`` calls.

    A Shape only needs ``db.fetch`` / ``db.fetch_one`` / ``db._driver`` etc., so a
    thin proxy is enough to count the queries a load issues. (``Database.fetch``
    itself is read-only, so it can't be monkeypatched in place.)
    """

    def __init__(self, real) -> None:
        self._real = real
        self.fetches = 0

    async def fetch(self, *args, **kwargs):
        self.fetches += 1
        return await self._real.fetch(*args, **kwargs)

    def __getattr__(self, name):
        return getattr(self._real, name)


def _errors(result, category: str | None = None):
    out = []
    for issue in result.issues:
        if getattr(issue.severity, "name", "") != "ERROR":
            continue
        if category is not None and getattr(issue, "category", None) != category:
            continue
        out.append(issue)
    return out


# ---------------------------------------------------------------------------
# 1. The verified SQL -> render contract
# ---------------------------------------------------------------------------


class TestVerifiedContract:
    def test_shipped_app_is_contract_clean(self, example_app) -> None:
        """The example passes shapecheck with zero ERRORs — every block reads
        only fields its bound Shape actually fetched."""
        result = check_hypermedia_surface(example_app)
        assert _errors(result) == []

    def test_drift_in_a_surface_contract_fails_loud(self, example_app) -> None:
        """Name a Shape that does not exist and shapecheck ERRORs at check time
        with a did-you-mean — drift never reaches a user as a blank page."""
        example_app.set_contract_check_data("surface_contracts", {"sidebar": "ProjcetDetail"})
        result = check_hypermedia_surface(example_app)
        drift = _errors(result, "shapecheck")
        assert drift, "expected a shapecheck registry-drift ERROR"
        blob = " ".join(f"{i.message} {i.details or ''}" for i in drift)
        assert "ProjcetDetail" in blob  # names the missing Shape
        assert "ProjectDetail" in blob  # did-you-mean suggests the real Shape


# ---------------------------------------------------------------------------
# 2. Tenant isolation you cannot forget
# ---------------------------------------------------------------------------


class TestTenantIsolation:
    async def test_dashboard_shows_your_workspace(self, example_app) -> None:
        async with TestClient(example_app) as client:
            r = await client.get("/")
            assert r.status == 200
            assert "Acme Inc" in r.text
            assert "Website Redesign" in r.text
            assert "Wireframes" in r.text
            assert "Ship it" in r.text  # a comment, batched per-task

    async def test_dashboard_never_leaks_another_tenant(self, example_app) -> None:
        async with TestClient(example_app) as client:
            r = await client.get("/")
            assert r.status == 200
            for foreign in ("TOP SECRET", "Globex", "Build the laser", "Sharks acquired"):
                assert foreign not in r.text, f"cross-tenant leak: {foreign!r}"

    async def test_cannot_open_another_tenants_project(self, example_app) -> None:
        """Project #3 belongs to workspace 2. Fetched by id but scoped to your
        workspace, it resolves to None — indistinguishable from 'no such project'."""
        async with TestClient(example_app) as client:
            r = await client.get("/projects/3")
            assert r.status == 404
            assert "TOP SECRET" not in r.text

    async def test_scope_isolates_at_the_data_layer(self, example_module) -> None:
        """The killer guarantee: the same Shape, two tenants, zero overlap — and
        nobody wrote a `WHERE workspace_id = ...` clause."""
        app = example_module.app
        async with TestClient(app):
            mine = await Shape.fetch(example_module.Project, app.db, scope=1)
            theirs = await Shape.fetch(example_module.Project, app.db, scope=2)

        mine_ids = {p.id for p in mine}
        theirs_ids = {p.id for p in theirs}
        assert mine_ids == {1, 2}
        assert theirs_ids == {3}
        assert mine_ids.isdisjoint(theirs_ids)
        assert all("TOP SECRET" not in p.name for p in mine)


# ---------------------------------------------------------------------------
# 3. No N+1
# ---------------------------------------------------------------------------


class TestBoundedQueries:
    async def test_dashboard_query_count_is_bounded(self, example_module) -> None:
        """The dashboard composite loads projects -> tasks -> comments plus a
        recent feed in ONE query per level, and the count does not grow when the
        data does."""
        app = example_module.app
        async with TestClient(app):
            # `Database.fetch` is read-only, so count via a thin forwarding proxy
            # passed in place of the db — exactly how a Shape receives its db.
            counter = _CountingDB(app.db)

            # Baseline: projects(1) + tasks(1) + comments(1) + recent(1) = 4.
            await Composite.load(example_module.Dashboard, counter, scope=1)
            baseline = counter.fetches
            assert baseline == 4

            # Pile on far more rows for the same tenant...
            for i in range(50):
                await app.db.execute(
                    "INSERT INTO tasks (project_id, workspace_id, title, priority, done, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    1,
                    1,
                    f"extra task {i}",
                    1,
                    0,
                    "2026-02-01",
                )

            counter.fetches = 0
            await Composite.load(example_module.Dashboard, counter, scope=1)
            # ...and the query count is unchanged — bounded, not one-per-row.
            assert counter.fetches == baseline


# ---------------------------------------------------------------------------
# Behavior: project detail
# ---------------------------------------------------------------------------


class TestProjectDetail:
    async def test_detail_renders(self, example_app) -> None:
        async with TestClient(example_app) as client:
            r = await client.get("/projects/1")
            assert r.status == 200
            assert "Website Redesign" in r.text
            assert "Wireframes" in r.text
