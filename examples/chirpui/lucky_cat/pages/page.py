"""Markets-grid landing — GET /.

#222 renders the brand + a live markets grid driven by the deterministic
``SimFeed``. ``markets`` and ``tickers`` are provided by ``_context.py``.
"""

from chirp import Page


def get(markets, tickers, sparklines) -> Page:
    return Page(
        "page.html",
        "page_content",
        page_block_name="page_root",
        markets=markets,
        tickers=tickers,
        sparklines=sparklines,
    )
