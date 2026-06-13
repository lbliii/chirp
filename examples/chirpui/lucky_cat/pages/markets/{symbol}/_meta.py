"""Route metadata for the market-detail route.

RouteMeta fields are static strings (no per-request context interpolation), so
the live symbol shows in the page H1 / ticker rather than the title here.
"""

from chirp.pages.types import RouteMeta

META = RouteMeta(title="Market", breadcrumb_label="Market")
