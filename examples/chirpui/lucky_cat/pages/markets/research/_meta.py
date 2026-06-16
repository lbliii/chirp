"""Route metadata for Markets → Research.

RouteMeta fields are static strings (no per-request interpolation); the active
query / sort / page live in the URL params + the page body, not the title.
"""

from chirp.pages.types import RouteMeta

META = RouteMeta(title="Research", breadcrumb_label="Research")
