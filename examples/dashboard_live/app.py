"""Live Sales Dashboard — real-time data layer showcase.

Demonstrates the full chirp data pipeline:
- App(db=..., migrations=...) — zero-boilerplate database setup
- SQL in, frozen dataclasses out — no ORM
- Transactions — atomic multi-statement operations
- Suspense page load — shell with skeletons first, data blocks streamed in
- SSE live updates — new orders push HTML fragments to the browser
- Zero JavaScript — htmx handles everything

The same pattern works with PostgreSQL LISTEN/NOTIFY for true
database-driven real-time (see db.listen() in chirp.data docs).

Run:
    python app.py
"""

import asyncio
import os
import random
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from chirp import App, AppConfig, EventStream, Fragment, Suspense
from chirp.data import Query

TEMPLATES_DIR = Path(__file__).parent / "templates"
MIGRATIONS_DIR = Path(__file__).parent / "migrations"
DB_PATH = Path(os.environ.get("CHIRP_DASHBOARD_DB", str(Path(__file__).parent / "dashboard.db")))

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


# Reusable base query — immutable, safe to define at module level
ORDERS = Query(Order, "orders")

# ---------------------------------------------------------------------------
# Seed data — populate the database on first run
# ---------------------------------------------------------------------------


@app.on_startup
async def seed_data():
    """Insert sample orders if the table is empty."""
    count = await ORDERS.count(app.db)
    if count > 0:
        return

    now = datetime.now(UTC)
    rows = []
    for _i in range(12):
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
    total = await ORDERS.count(app.db)
    revenue = await app.db.fetch_val("SELECT COALESCE(SUM(amount), 0) FROM orders") or 0.0
    pending = await ORDERS.where("status = ?", "pending").count(app.db)
    avg = round(revenue / total, 2) if total > 0 else 0.0
    return Stats(
        total_orders=total,
        total_revenue=round(float(revenue), 2),
        pending_count=pending,
        avg_order=avg,
    )


async def get_recent_orders(limit: int = 10) -> list[Order]:
    """Fetch the most recent orders."""
    return await ORDERS.order_by("id DESC").take(limit).fetch(app.db)


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
        order = await ORDERS.order_by("id DESC").fetch_one(app.db)

    assert order is not None
    return order


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.route("/")
async def index():
    """Full dashboard page — shell renders instantly, data streams in.

    Suspense sends the page skeleton immediately (with "—" placeholders
    and "Loading orders..." text), then resolves stats and orders from
    the database concurrently and streams them as OOB block swaps.
    """
    return Suspense("dashboard.html", stats=get_stats(), orders=get_recent_orders())


@app.route("/events", referenced=True)
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
