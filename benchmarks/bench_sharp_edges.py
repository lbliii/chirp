"""Sprint 0 baselines for the sharp-edges epic.

Measures happy-path performance for the three systems we'll modify:
1. Suspense shell-to-first-byte (10 deferred blocks)
2. ReactiveBus throughput (1000 events, 10 subscribers)
3. Route matching latency (100 parameterized routes)

Run:
    uv run python -m benchmarks.bench_sharp_edges

Output: JSON baseline saved to benchmarks/baseline_sharp_edges.json
"""

from __future__ import annotations

import asyncio
import json
import statistics
import time
from pathlib import Path

# ---------------------------------------------------------------------------
# 1. ReactiveBus throughput
# ---------------------------------------------------------------------------


async def bench_reactive_bus(events: int = 1000, subscribers: int = 10) -> dict:
    """Measure emit throughput with N subscribers draining concurrently."""
    from chirp.pages.reactive import ChangeEvent, ReactiveBus

    bus = ReactiveBus(maxsize=events + 1)
    counts: list[int] = [0] * subscribers

    async def drain(idx: int, scope: str) -> None:
        count = 0
        async for _event in bus.subscribe(scope):
            count += 1
        counts[idx] = count

    # Start subscriber tasks
    tasks = [asyncio.create_task(drain(i, "bench")) for i in range(subscribers)]

    # Small yield to let subscribers register
    await asyncio.sleep(0.01)

    # Emit
    t0 = time.perf_counter()
    for n in range(events):
        bus.emit_sync(ChangeEvent(scope="bench", changed_paths=frozenset({f"p{n}"})))
    emit_elapsed = time.perf_counter() - t0

    # Let subscribers drain, then close
    await asyncio.sleep(0.05)
    bus.close("bench")
    await asyncio.gather(*tasks)

    total_delivered = sum(counts)
    return {
        "name": "reactive_bus_throughput",
        "events_emitted": events,
        "subscribers": subscribers,
        "total_delivered": total_delivered,
        "dropped": bus.dropped_count,
        "emit_time_ms": round(emit_elapsed * 1000, 3),
        "events_per_sec": round(events / emit_elapsed) if emit_elapsed > 0 else 0,
    }


# ---------------------------------------------------------------------------
# 2. Route matching latency
# ---------------------------------------------------------------------------


def bench_route_matching(num_routes: int = 100, lookups: int = 5000) -> dict:
    """Measure trie-based route matching with parameterized routes."""
    from chirp.routing.route import Route
    from chirp.routing.router import Router

    router = Router()

    # Register N routes: /items/{id}/sub0, ... /items/{id}/subN
    async def noop(_request):
        return "ok"

    for i in range(num_routes):
        router.add(
            Route(
                path=f"/items/{{id}}/sub{i}",
                handler=noop,
                methods=frozenset({"GET"}),
            )
        )

    router.compile()

    # Warm up
    for _ in range(100):
        router.match("GET", "/items/42/sub50")

    # Measure
    latencies = []
    for i in range(lookups):
        path = f"/items/{i % 999}/sub{i % num_routes}"
        t0 = time.perf_counter()
        router.match("GET", path)
        latencies.append(time.perf_counter() - t0)

    latencies_us = [t * 1_000_000 for t in latencies]
    return {
        "name": "route_matching",
        "num_routes": num_routes,
        "lookups": lookups,
        "avg_us": round(statistics.mean(latencies_us), 3),
        "p50_us": round(statistics.median(latencies_us), 3),
        "p99_us": round(sorted(latencies_us)[int(lookups * 0.99)], 3),
    }


# ---------------------------------------------------------------------------
# 3. Suspense shell render latency
# ---------------------------------------------------------------------------


async def bench_suspense_shell(num_deferred: int = 10) -> dict:
    """Measure time-to-first-chunk for Suspense with N deferred blocks.

    Uses a minimal in-memory Kida environment with synthetic blocks.
    """
    from kida import DictLoader, Environment

    from chirp.templating.returns import Suspense
    from chirp.templating.suspense import render_suspense

    # Build a template with N blocks that depend on deferred keys
    block_defs = [
        f"{{% block panel_{i} %}}"
        f"{{% if d_{i} is not none %}}{{{{ d_{i} }}}}{{% else %}}loading...{{% endif %}}"
        f"{{% endblock %}}"
        for i in range(num_deferred)
    ]
    template_src = "<html><body>" + "\n".join(block_defs) + "</body></html>"

    env = Environment(loader=DictLoader({"bench_suspense.html": template_src}))

    # Build Suspense with N deferred awaitables
    async def slow_value(v: str) -> str:
        await asyncio.sleep(0.001)  # 1ms simulated latency
        return v

    iterations = 200
    shell_latencies = []
    total_latencies = []

    for _ in range(iterations):
        ctx = {f"d_{i}": slow_value(f"val_{i}") for i in range(num_deferred)}
        suspense = Suspense(
            "bench_suspense.html",
            defer_blocks=tuple(f"panel_{i}" for i in range(num_deferred)),
            **ctx,
        )

        t0 = time.perf_counter()
        chunks = []
        async for chunk in render_suspense(env, suspense, is_htmx=True):
            if not chunks:
                shell_latencies.append(time.perf_counter() - t0)
            chunks.append(chunk)
        total_latencies.append(time.perf_counter() - t0)

    shell_us = [t * 1_000_000 for t in shell_latencies]
    total_ms = [t * 1000 for t in total_latencies]
    return {
        "name": "suspense_shell_render",
        "deferred_blocks": num_deferred,
        "iterations": iterations,
        "shell_avg_us": round(statistics.mean(shell_us), 3),
        "shell_p50_us": round(statistics.median(shell_us), 3),
        "shell_p99_us": round(sorted(shell_us)[int(iterations * 0.99)], 3),
        "total_avg_ms": round(statistics.mean(total_ms), 3),
        "total_p99_ms": round(sorted(total_ms)[int(iterations * 0.99)], 3),
    }


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


async def main() -> None:
    results = []

    print("Benchmarking ReactiveBus throughput...", flush=True)
    results.append(await bench_reactive_bus())

    print("Benchmarking route matching...", flush=True)
    results.append(bench_route_matching())

    print("Benchmarking Suspense shell render...", flush=True)
    results.append(await bench_suspense_shell())

    # Print results
    for r in results:
        print(f"\n--- {r['name']} ---")
        for k, v in r.items():
            if k != "name":
                print(f"  {k}: {v}")

    # Save baseline
    out = Path(__file__).parent / "baseline_sharp_edges.json"
    out.write_text(json.dumps(results, indent=2) + "\n")
    print(f"\nBaseline saved to {out}")


if __name__ == "__main__":
    asyncio.run(main())
