"""Symbol maps between Lucky Cat's house-token pairs and upstream APIs."""

from __future__ import annotations

# Lucky Cat symbol -> Kraken v2 pair name (USD quoted; displayed as $MEOW).
KRAKEN_PAIRS: dict[str, str] = {
    "BTC-MEOW": "BTC/USD",
    "ETH-MEOW": "ETH/USD",
    "SOL-MEOW": "SOL/USD",
    "DOGE-MEOW": "DOGE/USD",
}

KRAKEN_TO_LC: dict[str, str] = {v: k for k, v in KRAKEN_PAIRS.items()}

# Lucky Cat symbol -> CoinGecko coin id (simple/price + ohlc endpoints).
COINGECKO_IDS: dict[str, str] = {
    "BTC-MEOW": "bitcoin",
    "ETH-MEOW": "ethereum",
    "SOL-MEOW": "solana",
    "DOGE-MEOW": "dogecoin",
}

USER_AGENT = "LuckyCat-ChirpDemo/1.0 (+https://github.com/lbliii/chirp)"
