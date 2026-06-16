"""Markets scale-prep regression tests for Lucky Cat (#278, PR8).

Three things break at a 500-coin catalog; PR8 fixes all of them behind the
``LUCKY_CAT_CATALOG`` env gate so the determinism golden
(``test_feed_determinism.py``, seed ``0xCA7``) stays green at the default 6:

  * the synthetic catalog grows the market list deterministically WITHOUT
    perturbing the shipped six (so the golden holds);
  * the SimFeed ThreadPool fan-out stays a bounded width (it must NOT spawn one
    OS thread per coin); and
  * the root context maps (``tickers`` / ``sparklines``) are LAZY — they compute
    + cache per symbol on access instead of building every market on every
    request.

Imports are **in-body** (not top-of-module): the autouse ``_lucky_cat_on_path``
fixture in ``conftest.py`` only puts the example dir on ``sys.path`` during test
*execution*, not collection — same reason ``test_feed_determinism.py`` /
``test_query.py`` import in-body. Each ``SimFeed`` is constructed locally (never
``get_feed()``) so the env-gated catalog and the shared app feed never collide.
Runs in <1s (watchdog-safe).
"""

import pytest

pytestmark = pytest.mark.issue(278)


# ---------------------------------------------------------------------------
# Env-gated synthetic catalog — default is exactly the shipped six.
# ---------------------------------------------------------------------------


class TestSyntheticCatalog:
    def test_default_catalog_is_the_shipped_six(self, monkeypatch) -> None:
        """Unset env => the resolved defs are the shipped six verbatim, in order.

        This is the load-bearing guard for the determinism golden: if the default
        catalog ever drifts from ``_MARKET_DEFS``, the warmed ``0xCA7`` snapshot
        in ``test_feed_determinism.py`` changes too.
        """
        from feed import _MARKET_DEFS, DEFAULT_SEED, SimFeed

        monkeypatch.delenv("LUCKY_CAT_CATALOG", raising=False)
        feed = SimFeed(seed=DEFAULT_SEED, tick_interval=0)
        assert feed._defs == _MARKET_DEFS
        assert feed.market_count == len(_MARKET_DEFS) == 6
        assert [m.symbol for m in feed.markets()] == [d[0] for d in _MARKET_DEFS]

    def test_small_n_does_not_shrink_below_the_six(self, monkeypatch) -> None:
        """N <= 6 is a no-op: the catalog never drops below the shipped six."""
        from feed import _MARKET_DEFS, DEFAULT_SEED, SimFeed

        monkeypatch.setenv("LUCKY_CAT_CATALOG", "3")
        feed = SimFeed(seed=DEFAULT_SEED, tick_interval=0)
        assert feed._defs == _MARKET_DEFS

    def test_invalid_env_falls_back_to_default(self, monkeypatch) -> None:
        from feed import _MARKET_DEFS, DEFAULT_SEED, SimFeed

        monkeypatch.setenv("LUCKY_CAT_CATALOG", "not-an-int")
        feed = SimFeed(seed=DEFAULT_SEED, tick_interval=0)
        assert feed._defs == _MARKET_DEFS

    def test_large_n_grows_catalog_and_preserves_the_six(self, monkeypatch) -> None:
        """N > 6 appends (N-6) synthetic defs, leaving the shipped six untouched."""
        from feed import _MARKET_DEFS, DEFAULT_SEED, SimFeed

        monkeypatch.setenv("LUCKY_CAT_CATALOG", "50")
        feed = SimFeed(seed=DEFAULT_SEED, tick_interval=0)
        assert feed.market_count == 50
        # The shipped six are still the first six, verbatim and in order.
        assert feed._defs[: len(_MARKET_DEFS)] == _MARKET_DEFS
        # Every symbol is unique (no collision between shipped + synthetic).
        symbols = [m.symbol for m in feed.markets()]
        assert len(symbols) == len(set(symbols)) == 50

    def test_synthetic_defs_are_deterministic_per_index(self, monkeypatch) -> None:
        """Two independent constructions at the same N yield the IDENTICAL tail —
        the synthetic defs derive purely from the index (no RNG ordering)."""
        from feed import DEFAULT_SEED, SimFeed

        monkeypatch.setenv("LUCKY_CAT_CATALOG", "20")
        a = SimFeed(seed=DEFAULT_SEED, tick_interval=0)
        b = SimFeed(seed=DEFAULT_SEED, tick_interval=0)
        assert a._defs == b._defs

    def test_synthetic_feed_is_queryable(self, monkeypatch) -> None:
        """A synthetic symbol resolves through the full snapshot surface after a
        warm — the env-gated catalog is a real, usable feed, not just a count."""
        from feed import _MARKET_DEFS, DEFAULT_SEED, SimFeed

        monkeypatch.setenv("LUCKY_CAT_CATALOG", "10")
        feed = SimFeed(seed=DEFAULT_SEED, tick_interval=0)
        feed.reset()
        feed.warm()
        syn = feed.markets()[len(_MARKET_DEFS)].symbol
        assert feed.has_symbol(syn)
        t = feed.ticker(syn)
        assert t.symbol == syn
        assert t.price > 0
        assert len(feed.candles(syn, interval="1H", limit=8)) > 0


# ---------------------------------------------------------------------------
# Bounded ThreadPool — a 500-coin catalog must NOT spawn 500 threads.
# ---------------------------------------------------------------------------


class TestBoundedPool:
    def test_default_pool_width_matches_six_markets(self, monkeypatch) -> None:
        """Default catalog keeps the proven 6-wide fan-out (worker_count unchanged
        — the free-threading proof, #227, stays honest)."""
        from feed import DEFAULT_SEED, SimFeed

        monkeypatch.delenv("LUCKY_CAT_CATALOG", raising=False)
        feed = SimFeed(seed=DEFAULT_SEED, tick_interval=0)
        assert feed.worker_count == 6

    def test_large_catalog_caps_pool_width(self, monkeypatch) -> None:
        """500 markets => the pool is bounded to 32 workers, NOT 500 threads.

        The cap is what keeps the engine honest at scale; the market COUNT still
        reflects the full catalog (one CPU task each), only the concurrency WIDTH
        is bounded.
        """
        from feed import DEFAULT_SEED, SimFeed

        monkeypatch.setenv("LUCKY_CAT_CATALOG", "500")
        feed = SimFeed(seed=DEFAULT_SEED, tick_interval=0)
        assert feed.market_count == 500
        assert feed.worker_count <= 32
        assert feed.worker_count == 32


# ---------------------------------------------------------------------------
# Lazy per-view context — computes on access, never the whole catalog eagerly.
# ---------------------------------------------------------------------------


class TestLazyContext:
    def test_lazy_map_computes_only_touched_symbols(self) -> None:
        """The lazy map builds + caches per symbol on access and never eagerly
        builds the whole catalog — the core scale fix for ``context()``."""
        from pages._context import _LazySymbolMap

        built: list[str] = []

        def build(symbol: str) -> str:
            built.append(symbol)
            return f"value:{symbol}"

        m = _LazySymbolMap(("A", "B", "C"), build)
        # Construction touches nothing.
        assert built == []
        # Indexing one symbol builds exactly that one.
        assert m["B"] == "value:B"
        assert built == ["B"]
        # A second read of the same symbol is cached — no rebuild.
        assert m["B"] == "value:B"
        assert built == ["B"]
        # A different symbol builds just that one.
        assert m.get("A") == "value:A"
        assert built == ["B", "A"]

    def test_lazy_map_behaves_like_a_mapping(self) -> None:
        """``.get`` / ``in`` / ``len`` / truthiness match the dict the templates
        and ``navigation.py`` (``tickers = tickers or {}``) expect — and absent-key
        access never triggers a build."""
        from pages._context import _LazySymbolMap

        built: list[str] = []
        m = _LazySymbolMap(("A", "B"), lambda s: built.append(s) or s)
        assert len(m) == 2
        assert bool(m) is True  # non-empty -> truthy -> survives `tickers or {}`
        assert ("A" in m) is True
        assert ("Z" in m) is False
        # Absent key: default returned, NO build triggered.
        assert m.get("Z") is None
        assert m.get("Z", "fallback") == "fallback"
        assert built == []

    def test_empty_lazy_map_is_falsy(self) -> None:
        from pages._context import _LazySymbolMap

        m = _LazySymbolMap((), lambda s: s)
        assert len(m) == 0
        assert bool(m) is False

    def test_context_maps_are_lazy_not_eager_dicts(self, monkeypatch) -> None:
        """``context()`` returns lazy maps that compute on access, so the per-view
        build is O(rendered symbols), not O(catalog). Built against a fresh
        feed so this never depends on prior eager population."""
        import feed as feed_mod
        from pages._context import _LazySymbolMap, context

        monkeypatch.delenv("LUCKY_CAT_CATALOG", raising=False)
        feed_mod.reset()  # known warmed state for the shared app feed
        ctx = context()
        tickers = ctx["tickers"]
        sparklines = ctx["sparklines"]
        assert isinstance(tickers, _LazySymbolMap)
        assert isinstance(sparklines, _LazySymbolMap)
        # The cheap markets list stays eager.
        assert len(ctx["markets"]) == 6
        # Indexing resolves a real snapshot for a known symbol; an unknown symbol
        # is a clean miss (no build, no KeyError leak through .get).
        sym = ctx["markets"][0].symbol
        assert tickers.get(sym).symbol == sym
        assert sparklines[sym].ok is True
        assert tickers.get("NOPE-MEOW") is None
