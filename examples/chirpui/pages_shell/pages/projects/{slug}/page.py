import asyncio

from chirp import Request, Suspense


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


def get(project: dict[str, str], request: Request) -> Suspense:
    tab = (request.query.get("tab") or "").strip() or "overview"
    return Suspense(
        "projects/{slug}/page.html",
        defer_map={"stats": "project-stats", "activity": "project-activity"},
        project=project,
        active_tab=tab,
        stats=_load_stats(project),
        activity=_load_activity(project),
    )
