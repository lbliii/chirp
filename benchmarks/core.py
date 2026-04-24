"""Core Chirp benchmark workloads with reproducible JSON output.

These benchmarks measure framework-internal hot paths without starting a
network server. They are meant for regression tracking, not public comparison
claims against other frameworks.

Run:
    uv run python -m benchmarks.core
    uv run python -m benchmarks.core --iterations 50 --output /tmp/chirp-core.json
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import platform
import statistics
import sys
import tempfile
import time
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from importlib import metadata
from pathlib import Path
from typing import Any

from kida import DictLoader, Environment

from chirp.realtime.events import SSEEvent
from chirp.routing.route import Route
from chirp.routing.router import Router
from chirp.server.negotiation import negotiate
from chirp.templating.integration import render_fragment
from chirp.templating.returns import OOB, Fragment, Suspense, Template
from chirp.templating.suspense import DEFERRED, render_suspense
from chirp.tools.events import ToolCallEvent, ToolEventBus

DEFAULT_ITERATIONS = 250
DEFAULT_ROUTE_COUNT = 100


def _package_version(name: str) -> str | None:
    with contextlib.suppress(metadata.PackageNotFoundError):
        return metadata.version(name)
    return None


def environment_metadata() -> dict[str, Any]:
    """Return versioned environment metadata for benchmark artifacts."""
    try:
        gil_enabled = sys._is_gil_enabled()
    except AttributeError:
        gil_enabled = True
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "python": {
            "version": platform.python_version(),
            "implementation": platform.python_implementation(),
            "cache_tag": sys.implementation.cache_tag,
            "gil_enabled": gil_enabled,
            "free_threaded": not gil_enabled,
        },
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "processor": platform.processor(),
        },
        "packages": {
            "bengal-chirp": _package_version("bengal-chirp"),
            "bengal-pounce": _package_version("bengal-pounce"),
            "kida-templates": _package_version("kida-templates"),
        },
    }


def _percentiles(samples: list[float]) -> dict[str, float]:
    ordered = sorted(samples)
    n = len(ordered)
    return {
        "avg_us": round(statistics.mean(ordered), 3),
        "p50_us": round(ordered[n // 2], 3),
        "p99_us": round(ordered[min(n - 1, int(n * 0.99))], 3),
    }


def _measure_sync(
    name: str,
    iterations: int,
    func: Callable[[], object],
    *,
    warmup: int = 25,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    for _ in range(warmup):
        func()
    samples: list[float] = []
    for _ in range(iterations):
        t0 = time.perf_counter()
        func()
        samples.append((time.perf_counter() - t0) * 1_000_000)
    result = {
        "name": name,
        "kind": "sync",
        "iterations": iterations,
        **_percentiles(samples),
    }
    if extra:
        result.update(extra)
    return result


async def _measure_async(
    name: str,
    iterations: int,
    func: Callable[[], Awaitable[object]],
    *,
    warmup: int = 10,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    for _ in range(warmup):
        await func()
    samples: list[float] = []
    for _ in range(iterations):
        t0 = time.perf_counter()
        await func()
        samples.append((time.perf_counter() - t0) * 1_000_000)
    result = {
        "name": name,
        "kind": "async",
        "iterations": iterations,
        **_percentiles(samples),
    }
    if extra:
        result.update(extra)
    return result


def _template_env() -> Environment:
    env = Environment(
        loader=DictLoader(
            {
                "bench.html": """
<main>
  {% block content %}<section id="content"><h1>{{ title }}</h1><p>{{ body }}</p></section>{% endblock %}
  {% block badge %}<span id="badge">{{ count }}</span>{% endblock %}
  {% block toast %}<aside id="toast">{{ message }}</aside>{% endblock %}
  {% block panel_0 %}{% if d_0 is deferred %}<div>Loading 0</div>{% else %}<div>{{ d_0 }}</div>{% endif %}{% endblock %}
  {% block panel_1 %}{% if d_1 is deferred %}<div>Loading 1</div>{% else %}<div>{{ d_1 }}</div>{% endif %}{% endblock %}
  {% block panel_2 %}{% if d_2 is deferred %}<div>Loading 2</div>{% else %}<div>{{ d_2 }}</div>{% endif %}{% endblock %}
</main>
""".strip()
            }
        )
    )
    env.add_test("deferred", lambda value: value is DEFERRED)
    return env


def bench_template_render(iterations: int) -> dict[str, Any]:
    env = _template_env()
    value = Template(
        "bench.html",
        title="Chirp",
        body="HTML over the wire",
        count=42,
        message="Saved",
        d_0="a",
        d_1="b",
        d_2="c",
    )

    def render() -> str:
        response = negotiate(value, kida_env=env)
        return response.text

    return _measure_sync("template_render", iterations, render)


def bench_fragment_render(iterations: int) -> dict[str, Any]:
    env = _template_env()
    fragment = Fragment(
        "bench.html",
        "content",
        title="Chirp",
        body="Fragment swap",
        count=42,
        message="Saved",
        d_0="a",
        d_1="b",
        d_2="c",
    )
    return _measure_sync(
        "fragment_render",
        iterations,
        lambda: render_fragment(env, fragment),
        extra={"block": "content"},
    )


def bench_oob_serialization(iterations: int) -> dict[str, Any]:
    env = _template_env()
    value = OOB(
        Fragment(
            "bench.html",
            "content",
            title="Chirp",
            body="Primary swap",
            count=42,
            message="Saved",
            d_0="a",
            d_1="b",
            d_2="c",
        ),
        Fragment("bench.html", "badge", count=43),
        Fragment("bench.html", "toast", message="Saved"),
    )

    def render() -> str:
        response = negotiate(value, kida_env=env)
        return response.text

    return _measure_sync(
        "oob_serialization",
        iterations,
        render,
        extra={"oob_fragments": 2},
    )


async def bench_suspense_first_chunk(iterations: int) -> dict[str, Any]:
    env = _template_env()

    async def value(name: str) -> str:
        await asyncio.sleep(0)
        return name

    async def render_once() -> float:
        suspense = Suspense(
            "bench.html",
            defer_blocks=("panel_0", "panel_1", "panel_2"),
            title="Chirp",
            body="Suspense",
            count=42,
            message="Saved",
            d_0=value("alpha"),
            d_1=value("beta"),
            d_2=value("gamma"),
        )
        t0 = time.perf_counter()
        first_chunk_us: float | None = None
        async for chunk in render_suspense(env, suspense, is_htmx=True):
            if first_chunk_us is None:
                first_chunk_us = (time.perf_counter() - t0) * 1_000_000
                assert chunk
        return first_chunk_us or 0.0

    for _ in range(10):
        await render_once()
    samples = [await render_once() for _ in range(iterations)]
    return {
        "name": "suspense_first_chunk",
        "kind": "async",
        "iterations": iterations,
        **_percentiles(samples),
        "deferred_blocks": 3,
    }


async def bench_sse_fanout(iterations: int, *, subscribers: int = 8) -> dict[str, Any]:
    bus = ToolEventBus()
    counts = [0] * subscribers

    async def drain(index: int) -> None:
        async for event in bus.subscribe():
            SSEEvent(data=event.tool_name, event="tool-call", id=event.call_id).encode()
            counts[index] += 1

    tasks = [asyncio.create_task(drain(i)) for i in range(subscribers)]
    await asyncio.sleep(0)

    result = await _measure_async(
        "sse_fanout",
        iterations,
        lambda: bus.emit(
            ToolCallEvent(
                tool_name="search",
                arguments={"q": "chirp"},
                result={"ok": True},
                timestamp=time.time(),
            )
        ),
        warmup=0,
        extra={"subscribers": subscribers},
    )

    await asyncio.sleep(0)
    bus.close()
    await asyncio.gather(*tasks)
    result["events_delivered"] = sum(counts)
    result["expected_deliveries"] = iterations * subscribers
    return result


def bench_filesystem_route_dispatch(iterations: int, *, route_count: int) -> dict[str, Any]:
    from chirp.pages.discovery import discover_pages

    with tempfile.TemporaryDirectory(prefix="chirp-bench-pages-") as tmp:
        pages = Path(tmp)
        for index in range(route_count):
            route_dir = pages / f"topic{index}"
            route_dir.mkdir()
            (route_dir / "page.py").write_text(
                "from chirp import Page\n\n"
                "def get():\n"
                "    return Page('page.html', 'content', title='Topic')\n",
                encoding="utf-8",
            )
            (route_dir / "page.html").write_text(
                "{% block content %}{{ title }}{% endblock %}\n",
                encoding="utf-8",
            )

        discovered = discover_pages(pages)
        router = Router()
        for page_route in discovered:
            router.add(
                Route(
                    path=page_route.url_path,
                    handler=page_route.handler,
                    methods=page_route.methods,
                )
            )
        router.compile()

        paths = [f"/topic{i}" for i in range(route_count)]
        cursor = 0

        def match() -> object:
            nonlocal cursor
            path = paths[cursor % route_count]
            cursor += 1
            return router.match("GET", path)

        return _measure_sync(
            "filesystem_route_dispatch",
            iterations,
            match,
            extra={"routes": route_count},
        )


async def run_core_benchmarks(
    *,
    iterations: int = DEFAULT_ITERATIONS,
    route_count: int = DEFAULT_ROUTE_COUNT,
) -> dict[str, Any]:
    """Run all core workloads and return a JSON-serializable report."""
    if iterations < 1:
        msg = f"iterations must be >= 1, got {iterations}"
        raise ValueError(msg)
    if route_count < 1:
        msg = f"route_count must be >= 1, got {route_count}"
        raise ValueError(msg)

    workloads: list[dict[str, Any]] = [
        bench_template_render(iterations),
        bench_fragment_render(iterations),
        bench_oob_serialization(iterations),
        await bench_suspense_first_chunk(iterations),
        await bench_sse_fanout(iterations),
        bench_filesystem_route_dispatch(iterations, route_count=route_count),
    ]
    return {
        "schema_version": 1,
        "suite": "chirp-core",
        "environment": environment_metadata(),
        "config": {
            "iterations": iterations,
            "route_count": route_count,
            "timer": "time.perf_counter",
            "units": "microseconds",
        },
        "workloads": workloads,
    }


def write_report(report: dict[str, Any], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")


async def _main_async(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Chirp core benchmark workloads")
    parser.add_argument(
        "--iterations",
        "-n",
        type=int,
        default=DEFAULT_ITERATIONS,
        help=f"Iterations per workload (default: {DEFAULT_ITERATIONS})",
    )
    parser.add_argument(
        "--route-count",
        type=int,
        default=DEFAULT_ROUTE_COUNT,
        help=f"Filesystem routes to generate (default: {DEFAULT_ROUTE_COUNT})",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=Path(".benchmarks/core-latest.json"),
        help="JSON artifact path (default: .benchmarks/core-latest.json)",
    )
    args = parser.parse_args(argv)

    report = await run_core_benchmarks(
        iterations=args.iterations,
        route_count=args.route_count,
    )
    write_report(report, args.output)
    print(json.dumps(report, indent=2, sort_keys=True))
    print(f"\nBenchmark artifact written to {args.output}")
    return 0


def main() -> None:
    raise SystemExit(asyncio.run(_main_async()))


if __name__ == "__main__":
    main()
