"""Root context — stock data and page defaults."""

STOCKS = (
    {"symbol": "AAPL", "name": "Apple Inc.", "price": 178.72, "change": 2.34, "volume": "52.1M"},
    {"symbol": "GOOGL", "name": "Alphabet Inc.", "price": 141.80, "change": -0.95, "volume": "24.3M"},
    {"symbol": "MSFT", "name": "Microsoft Corp.", "price": 415.56, "change": 5.12, "volume": "18.7M"},
    {"symbol": "AMZN", "name": "Amazon.com Inc.", "price": 186.49, "change": 1.78, "volume": "31.2M"},
    {"symbol": "TSLA", "name": "Tesla Inc.", "price": 248.42, "change": -3.67, "volume": "45.8M"},
    {"symbol": "NVDA", "name": "NVIDIA Corp.", "price": 875.28, "change": 12.45, "volume": "38.9M"},
)


def context() -> dict:
    return {
        "page_title": "Stock Ticker",
        "breadcrumb_items": [{"label": "Overview", "href": "/"}],
        "stocks": STOCKS,
    }
