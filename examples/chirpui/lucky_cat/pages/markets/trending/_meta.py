"""Route metadata for Markets → Trending.

RouteMeta fields are static strings (no per-request interpolation); the active
segment shows in the page body, not the title.
"""

from chirp.pages.types import RouteMeta

META = RouteMeta(title="Trending", breadcrumb_label="Trending")
