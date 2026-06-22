"""Live feed adapter tests (#226) — offline with mocked upstream I/O."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from feed import FeedSource, SimFeed
from feed_adapters._helpers import map_kraken_ticker
from feed_adapters.kraken import KrakenFeed
from feed_adapters.mempool import ChainSnapshot, MempoolFeed


class TestFeedAdapterFactory:
    @pytest.mark.issue(226)
    def test_kraken_without_websockets_returns_none(self, monkeypatch) -> None:
        import feed_adapters

        monkeypatch.setitem(__import__("sys").modules, "websockets", None)  # type: ignore[arg-type]
        with patch.dict("sys.modules", {"websockets": None}):
            # Force ImportError on websockets import inside build_adapter
            import builtins

            real_import = builtins.__import__

            def _fake_import(name, *args, **kwargs):
                if name == "websockets":
                    raise ImportError("no websockets")
                return real_import(name, *args, **kwargs)

            monkeypatch.setattr(builtins, "__import__", _fake_import)
            assert feed_adapters.build_adapter("kraken") is None

    def test_unknown_adapter_returns_none(self) -> None:
        from feed_adapters import build_adapter

        assert build_adapter("not-a-feed") is None


class TestKrakenFeedMapping:
    def test_maps_ticker_payload(self) -> None:
        row = {
            "symbol": "BTC/USD",
            "last": 65000.0,
            "change": 1200.0,
            "change_pct": 1.88,
            "high": 66000.0,
            "low": 63000.0,
            "volume": 123.4,
            "timestamp": "2026-06-22T12:00:00.000000Z",
        }
        ticker = map_kraken_ticker("BTC-MEOW", row)
        assert ticker.symbol == "BTC-MEOW"
        assert ticker.price == 65000.0
        assert ticker.change_pct_24h == 1.88


class TestKrakenFeedProtocol:
    @pytest.mark.issue(226)
    def test_implements_feedsource_and_delegates_trade_hooks(self) -> None:
        feed = KrakenFeed()
        assert isinstance(feed, FeedSource)
        symbol = feed.markets()[0].symbol
        before = feed.order_book(symbol, depth=4)
        feed.consume_depth(symbol, "buy", before.asks[0].size)
        after = feed.order_book(symbol, depth=4)
        assert after.asks[0].size < before.asks[0].size

    def test_handle_message_updates_live_ticker(self) -> None:
        feed = KrakenFeed()
        feed._handle_message(
            {
                "channel": "ticker",
                "data": [
                    {
                        "symbol": "BTC/USD",
                        "last": 65000.0,
                        "change": 100.0,
                        "change_pct": 0.15,
                        "high": 66000.0,
                        "low": 64000.0,
                        "volume": 10.0,
                        "timestamp": "2026-06-22T12:00:00.000000Z",
                    }
                ],
            }
        )
        ticker = feed.ticker("BTC-MEOW")
        assert ticker.price == 65000.0

    @pytest.mark.asyncio
    async def test_subscribe_yields_live_tick_when_started(self) -> None:
        feed = KrakenFeed()
        feed._start_ok = True
        feed._handle_message(
            {
                "channel": "ticker",
                "data": [
                    {
                        "symbol": "BTC/USD",
                        "last": 65000.0,
                        "change": 100.0,
                        "change_pct": 0.15,
                        "high": 66000.0,
                        "low": 64000.0,
                        "volume": 10.0,
                        "timestamp": "2026-06-22T12:00:00.000000Z",
                    }
                ],
            }
        )
        feed._handle_message(
            {
                "channel": "book",
                "data": [
                    {
                        "symbol": "BTC/USD",
                        "bids": [{"price": 64990.0, "qty": 1.0}],
                        "asks": [{"price": 65010.0, "qty": 1.0}],
                    }
                ],
            }
        )
        agen = feed.subscribe("BTC-MEOW")
        tick = await agen.__anext__()
        await agen.aclose()
        assert tick.symbol == "BTC-MEOW"
        assert tick.ticker.price == 65000.0
        assert tick.book.bids[0].price == 64990.0


class TestCoinGeckoFeedProtocol:
    @pytest.mark.asyncio
    async def test_refresh_maps_simple_price(self) -> None:
        from feed_adapters.coingecko import CoinGeckoFeed

        feed = CoinGeckoFeed()
        client = AsyncMock()
        response = MagicMock()
        response.raise_for_status = MagicMock()
        response.json.return_value = {
            "bitcoin": {"usd": 65000.0, "usd_24h_change": 1.5},
        }
        client.get = AsyncMock(return_value=response)
        await feed._refresh_once(client)
        ticker = feed.ticker("BTC-MEOW")
        assert ticker.price == 65000.0
        book = feed.order_book("BTC-MEOW", depth=4)
        assert len(book.bids) == 4


class TestMempoolFeedChainPanel:
    @pytest.mark.issue(226)
    def test_chain_snapshot_from_ws_payload(self) -> None:
        feed = MempoolFeed()
        feed._handle_message(
            {
                "fees": {"fastestFee": 12, "halfHourFee": 8, "hourFee": 6},
                "mempoolInfo": {"size": 150000, "bytes": 400000},
                "block": {"height": 900000, "tx_count": 2500},
            }
        )
        snap = feed.chain_snapshot()
        assert isinstance(snap, ChainSnapshot)
        assert snap.fastest_fee == 12
        assert snap.mempool_txs == 150000
        assert snap.block_height == 900000

    @pytest.mark.asyncio
    async def test_watch_chain_yields_snapshot(self) -> None:
        feed = MempoolFeed()
        feed._start_ok = True
        feed._handle_message(
            {
                "fees": {"fastestFee": 5, "halfHourFee": 4, "hourFee": 3},
                "mempoolInfo": {"size": 1000, "bytes": 4000},
            }
        )
        agen = feed.watch_chain()
        snap = await agen.__anext__()
        await agen.aclose()
        assert snap.fastest_fee == 5


class TestLiveFeedStartupFallback:
    @pytest.mark.asyncio
    async def test_start_failure_replaces_cache_with_sim(self, monkeypatch) -> None:
        import feed as feed_mod
        from feed_adapters.kraken import KrakenFeed

        monkeypatch.delenv("LUCKY_CAT_FEED", raising=False)
        feed_mod.reset()
        feed = KrakenFeed()
        feed_mod._feed = feed
        feed_mod._feed_name = "kraken"

        async def _fail_start() -> bool:
            return False

        monkeypatch.setattr(feed, "start", _fail_start)
        ok = await feed_mod.start_live_feed()
        assert ok is False
        assert isinstance(feed_mod.get_feed(), SimFeed)
        feed_mod.reset()
