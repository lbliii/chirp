"""Suspense Dashboard — instant shell, deferred data.

Demonstrates Chirp's Suspense return type: the page shell renders instantly
with skeleton placeholders, then slow data sources fill in as OOB swaps.
No client framework required.

Run:
    python app.py
"""

import asyncio
import random
from pathlib import Path

from chirp import App, AppConfig, Suspense

TEMPLATES_DIR = Path(__file__).parent / "templates"

config = AppConfig(template_dir=TEMPLATES_DIR, worker_mode="async")
app = App(config=config)


# ---------------------------------------------------------------------------
# Simulated slow data sources
# ---------------------------------------------------------------------------


async def load_revenue() -> dict:
    """Simulate a slow database query for revenue stats."""
    await asyncio.sleep(random.uniform(0.3, 0.8))
    return {
        "total": f"${random.randint(80, 120)},{random.randint(100, 999)}",
        "change": round(random.uniform(-5, 15), 1),
        "period": "last 30 days",
    }


async def load_orders() -> list[dict]:
    """Simulate a slow API call for recent orders."""
    await asyncio.sleep(random.uniform(0.5, 1.0))
    names = ["Alice", "Bob", "Charlie", "Diana", "Eve"]
    return [
        {
            "id": 1000 + i,
            "customer": random.choice(names),
            "amount": f"${random.randint(20, 500)}",
            "status": random.choice(["shipped", "processing", "delivered"]),
        }
        for i in range(5)
    ]


async def load_visitors() -> dict:
    """Simulate an analytics service call."""
    await asyncio.sleep(random.uniform(0.2, 0.6))
    return {
        "current": random.randint(80, 350),
        "peak_today": random.randint(400, 800),
        "source": random.choice(["organic", "referral", "direct"]),
    }


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.route("/")
def dashboard():
    """Shell renders instantly, data blocks fill in as they resolve."""
    return Suspense(
        "dashboard.html",
        title="Sales Dashboard",
        revenue=load_revenue(),
        orders=load_orders(),
        visitors=load_visitors(),
    )


if __name__ == "__main__":
    app.run()
