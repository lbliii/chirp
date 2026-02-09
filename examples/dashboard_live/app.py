"""Live Sales Dashboard — real-time data layer showcase.

Demonstrates the full chirp data pipeline:
- App(db=..., migrations=...) — zero-boilerplate database setup
- SQL in, frozen dataclasses out — no ORM
- Transactions — atomic multi-statement operations
- Streaming page load — shell first, data second
- SSE live updates — new orders push HTML fragments to the browser
- Zero JavaScript — htmx handles everything

The same pattern works with PostgreSQL LISTEN/NOTIFY for true
database-driven real-time (see db.listen() in chirp.data docs).

Run:
    python app.py
"""

import asyncio
import random
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from chirp import App, AppConfig, EventStream, Fragment, Template

TEMPLATES_DIR = Path(__file__).parent / "templates"
MIGRATIONS_DIR = Path(__file__).parent / "migrations"
DB_PATH = Path(__file__).parent / "dashboard.db"

app = App(
    config=AppConfig(template_dir=TEMPLATES_DIR, debug=True),
    db=f"sqlite:///{DB_PATH}",
    migrations=str(MIGRATIONS_DIR),
)

# ---------------------------------------------------------------------------
# Data models — frozen dataclasses, same objects from DB through to template
# ---------------------------------------------------------------------------

CUSTOMERS = ["Alice", "Bob", "Carol", "Dave", "Eve", "Frank", "Grace", "Hank"]
PRODUCTS = [
    ("Widget Pro", 29.99),
    ("Gadget X", 49.99),
    ("Turbo Kit", 99.99),
    ("Nano Pack", 14.99),
    ("Mega Bundle", 149.99),
    ("Starter Set", 19.99),
]


@dataclass(frozen=True, slots=True)
class Order:
    id: int
    customer: str
    product: str
    amount: float
    status: str
    created_at: str


@dataclass(frozen=True, slots=True)
class Stats:
    total_orders: int
    total_revenue: float
    pending_count: int
    avg_order: float


# ---------------------------------------------------------------------------
# Seed data — populate the database on first run
# ---------------------------------------------------------------------------


@app.on_startup
async def seed_data():
    """Insert sample orders if the table is empty."""
    count = await app.db.fetch_val("SELECT COUNT(*) FROM orders")
    if count > 0:
        return

    now = datetime.now(UTC)
    rows = []
    for i in range(12):
        customer = random.choice(CUSTOMERS)
        product, price = random.choice(PRODUCTS)
        status = random.choice(["pending", "shipped", "delivered"])
        ts = now.isoformat(timespec="seconds")
        rows.append((customer, product, price, status, ts))

    await app.db.execute_many(
        "INSERT INTO orders (customer, product, amount, status, created_at) VALUES (?, ?, ?, ?, ?)",
        rows,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def get_stats() -> Stats:
    """Compute dashboard statistics from the database."""
    total = await app.db.fetch_val("SELECT COUNT(*) FROM orders") or 0
    revenue = await app.db.fetch_val("SELECT COALESCE(SUM(amount), 0) FROM orders") or 0.0
    pending = await app.db.fetch_val("SELECT COUNT(*) FROM orders WHERE status = ?", "pending") or 0
    avg = round(revenue / total, 2) if total > 0 else 0.0
    return Stats(
        total_orders=int(total),
        total_revenue=round(float(revenue), 2),
        pending_count=int(pending),
        avg_order=avg,
    )


async def get_recent_orders(limit: int = 10) -> list[Order]:
    """Fetch the most recent orders."""
    return await app.db.fetch(
        Order,
        "SELECT * FROM orders ORDER BY id DESC LIMIT ?",
        limit,
    )


async def create_random_order() -> Order:
    """Insert a random order and return it."""
    customer = random.choice(CUSTOMERS)
    product, price = random.choice(PRODUCTS)
    now = datetime.now(UTC).isoformat(timespec="seconds")

    async with app.db.transaction():
        await app.db.execute(
            "INSERT INTO orders (customer, product, amount, status, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            customer,
            product,
            price,
            "pending",
            now,
        )
        order = await app.db.fetch_one(
            Order,
            "SELECT * FROM orders ORDER BY id DESC LIMIT 1",
        )

    assert order is not None
    return order


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.route("/")
async def index():
    """Full dashboard page — rendered from database."""
    stats = await get_stats()
    orders = await get_recent_orders()
    return Template("dashboard.html", stats=stats, orders=orders)


@app.route("/events")
def events():
    """Live order feed via Server-Sent Events.

    Simulates new orders arriving every 2-5 seconds. Each new order
    is inserted into the database and pushed as a rendered HTML fragment.

    With PostgreSQL, this would use db.listen("new_orders") instead of
    a polling loop — same pattern, real database triggers.
    """

    async def generate():
        while True:
            await asyncio.sleep(random.uniform(2.0, 5.0))

            # Create a new order in the database
            order = await create_random_order()
            stats = await get_stats()

            # Push rendered HTML fragments via SSE
            # htmx swaps these into the correct DOM locations
            yield Fragment("dashboard.html", "order_row", order=order)
            yield Fragment("dashboard.html", "stats_bar", stats=stats)

    return EventStream(generate())


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("Live Sales Dashboard")
    print("  http://127.0.0.1:8000")
    print()
    print("  Features:")
    print("    - App(db=..., migrations=...) — auto-connect + auto-migrate")
    print("    - SQL → frozen dataclass → template fragment → SSE → browser")
    print("    - Transactions for atomic inserts")
    print("    - Zero JavaScript (htmx)")
    print()
    app.run()
