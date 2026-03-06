import asyncio

from chirp import Suspense


async def _load_stats(project: dict[str, str]) -> tuple[dict[str, str], ...]:
    await asyncio.sleep(0)
    return (
        {"label": "Latency", "value": "42 ms"},
        {"label": "Deploys", "value": "18 this week"},
        {"label": "Health", "value": "99.98%"},
    )


async def _load_activity(project: dict[str, str]) -> tuple[str, ...]:
    await asyncio.sleep(0)
    return (
        f"{project['name']} passed layout-chain smoke tests.",
        "Shell actions updated during boosted navigation.",
        "Suspense blocks streamed into the detail view.",
    )


def get(project: dict[str, str]) -> Suspense:
    return Suspense(
        "projects/{slug}/page.html",
        defer_map={"stats": "project-stats", "activity": "project-activity"},
        project=project,
        stats=_load_stats(project),
        activity=_load_activity(project),
    )
