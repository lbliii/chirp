"""Weather Station Dashboard — full stack showcase.

Demonstrates the complete Pounce + Chirp + Kida pipeline:
streaming initial render, fragment caching, SSE-driven live updates,
and multi-worker free-threading. Open your browser and watch the data change.

Run:
    python app.py
"""

import asyncio
import random
import threading
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from chirp import App, AppConfig, EventStream, Fragment, SSEEvent, Stream, Template

TEMPLATES_DIR = Path(__file__).parent / "templates"

config = AppConfig(template_dir=TEMPLATES_DIR)
app = App(config=config)

# ---------------------------------------------------------------------------
# Sensor data model — thread-safe for free-threading
# ---------------------------------------------------------------------------

SENSORS = {
    "rooftop": "Rooftop",
    "garden": "Garden",
    "lakeside": "Lakeside",
    "hilltop": "Hilltop",
    "warehouse": "Warehouse",
    "parking": "Parking Lot",
}


@dataclass(frozen=True, slots=True)
class SensorReading:
    sensor_id: str
    location: str
    temp_c: float
    humidity: float
    wind_kph: float
    updated_at: str


_readings: dict[str, SensorReading] = {}
_lock = threading.Lock()


def _make_reading(sensor_id: str) -> SensorReading:
    """Generate a random reading for a sensor."""
    return SensorReading(
        sensor_id=sensor_id,
        location=SENSORS[sensor_id],
        temp_c=round(random.uniform(-5.0, 38.0), 1),
        humidity=round(random.uniform(20.0, 95.0), 1),
        wind_kph=round(random.uniform(0.0, 60.0), 1),
        updated_at=datetime.now(UTC).strftime("%H:%M:%S"),
    )


def _seed_readings() -> None:
    """Initialize all sensors with a first reading."""
    with _lock:
        for sensor_id in SENSORS:
            _readings[sensor_id] = _make_reading(sensor_id)


def _update_sensor(sensor_id: str) -> SensorReading:
    """Generate a new reading for one sensor and store it."""
    reading = _make_reading(sensor_id)
    with _lock:
        _readings[sensor_id] = reading
    return reading


def _get_all() -> dict[str, SensorReading]:
    """Return a snapshot of all current readings."""
    with _lock:
        return dict(_readings)


# Seed on module load so the initial page has data
_seed_readings()


# ---------------------------------------------------------------------------
# Template filters
# ---------------------------------------------------------------------------


@app.template_filter("avg_temp")
def avg_temp(readings: dict[str, SensorReading]) -> str:
    """Average temperature across all sensors."""
    if not readings:
        return "--"
    avg = sum(r.temp_c for r in readings.values()) / len(readings)
    return f"{avg:.1f}"


@app.template_filter("max_wind")
def max_wind(readings: dict[str, SensorReading]) -> str:
    """Maximum wind speed across all sensors."""
    if not readings:
        return "--"
    peak = max(r.wind_kph for r in readings.values())
    return f"{peak:.1f}"


# No custom sensor_count filter needed — using built-in ``| length`` in template.


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.route("/")
def index():
    """Full dashboard — rendered via Kida and served as a single response."""
    readings = _get_all()
    return Template("dashboard.html", readings=readings)


@app.route("/events")
def events():
    """Live sensor updates via Server-Sent Events.

    Each tick: pick a random sensor, generate a new reading, push the
    updated card and summary bar as rendered HTML fragments. htmx swaps
    the correct elements via out-of-band targeting (hx-swap-oob).
    """
    sensor_ids = list(SENSORS.keys())

    async def generate():
        while True:
            # Pick a random sensor and update it
            sensor_id = random.choice(sensor_ids)
            reading = _update_sensor(sensor_id)

            # Push the updated sensor card (OOB-swapped by ID)
            yield Fragment("dashboard.html", "sensor_card", reading=reading)

            # Push the updated summary bar (OOB-swapped by ID)
            yield Fragment("dashboard.html", "summary_bar", readings=_get_all())

            # Staggered updates: 0.8-2.5s between ticks
            await asyncio.sleep(random.uniform(0.8, 2.5))

    return EventStream(generate())


# ---------------------------------------------------------------------------
# Entry point — multi-worker Pounce for the full stack demo
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    try:
        from pounce import ServerConfig
        from pounce.server import Server

        app._ensure_frozen()
        config = ServerConfig(host="127.0.0.1", port=8000, workers=4)
        server = Server(config, app)
        print("Weather Station Dashboard")
        print("  http://127.0.0.1:8000")
        print("  4 worker threads (free-threading)")
        print()
        server.run()
    except ImportError:
        # Pounce not installed — fall back to single-worker dev server
        print("Weather Station Dashboard (single worker — install pounce for multi-worker)")
        app.run()
