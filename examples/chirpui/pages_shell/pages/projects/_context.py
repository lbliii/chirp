from chirp import ShellAction, ShellActions, ShellActionZone

PROJECTS = (
    {
        "slug": "apollo",
        "name": "Apollo",
        "summary": "Migrate the control plane to mounted pages and shell actions.",
        "status": "shipping",
        "owner": "Platform",
        "version": "2.4.1",
        "api_endpoints": (
            {"method": "GET", "path": "/api/projects", "description": "List all projects"},
            {"method": "POST", "path": "/api/projects", "description": "Create a new project"},
            {"method": "GET", "path": "/api/projects/:id", "description": "Get project details"},
            {"method": "PUT", "path": "/api/projects/:id", "description": "Update a project"},
            {"method": "DELETE", "path": "/api/projects/:id", "description": "Archive a project"},
        ),
        "changelog": (
            {
                "version": "2.4.1",
                "date": "2025-03-15",
                "description": "Fixed OOB region caching for nested routes",
            },
            {
                "version": "2.4.0",
                "date": "2025-03-01",
                "description": "Added shell action zones with merge/replace modes",
            },
            {
                "version": "2.3.0",
                "date": "2025-02-15",
                "description": "Suspense blocks for deferred content loading",
            },
        ),
    },
    {
        "slug": "beacon",
        "name": "Beacon",
        "summary": "Add live search, history-safe fragments, and request tracing.",
        "status": "active",
        "owner": "DX",
        "version": "1.2.0",
        "api_endpoints": (
            {
                "method": "GET",
                "path": "/api/search",
                "description": "Full-text search across projects",
            },
            {"method": "GET", "path": "/api/traces", "description": "List request traces"},
            {"method": "GET", "path": "/api/traces/:id", "description": "Get trace details"},
        ),
        "changelog": (
            {
                "version": "1.2.0",
                "date": "2025-03-10",
                "description": "Added fragment-safe history navigation",
            },
            {
                "version": "1.1.0",
                "date": "2025-02-20",
                "description": "Live search with debounce and highlight",
            },
            {
                "version": "1.0.0",
                "date": "2025-01-15",
                "description": "Initial release with request tracing",
            },
        ),
    },
    {
        "slug": "cosmos",
        "name": "Cosmos",
        "summary": "Prototype layout-chain suspense for a nested dashboard.",
        "status": "exploring",
        "owner": "Infra",
        "version": "0.3.0",
        "api_endpoints": (
            {"method": "GET", "path": "/api/dashboards", "description": "List dashboard layouts"},
            {"method": "GET", "path": "/api/widgets", "description": "List available widgets"},
            {
                "method": "POST",
                "path": "/api/dashboards/:id/widgets",
                "description": "Add widget to dashboard",
            },
        ),
        "changelog": (
            {
                "version": "0.3.0",
                "date": "2025-03-12",
                "description": "Nested suspense chains for widget loading",
            },
            {
                "version": "0.2.0",
                "date": "2025-02-28",
                "description": "Dashboard layout persistence",
            },
            {
                "version": "0.1.0",
                "date": "2025-02-01",
                "description": "Initial prototype with layout chains",
            },
        ),
    },
)


def context() -> dict:
    return {
        "projects": PROJECTS,
        "shell_actions": ShellActions(
            primary=ShellActionZone(
                items=(ShellAction(id="new-project", label="New project", href="/projects"),)
            ),
            overflow=ShellActionZone(
                items=(
                    ShellAction(id="docs", label="Routing docs", href="/projects"),
                    ShellAction(id="archive", label="Archive", href="/projects", icon="archive"),
                    ShellAction(id="export", label="Export", href="/projects", icon="export"),
                ),
            ),
        ),
    }
