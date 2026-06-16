"""Route metadata for Markets → Favorites — the starred-markets view.

Moved from ``/watchlist`` (#282): Favorites is now one of the four fixed Markets
destinations, so it lives under the ``/markets`` tree as a static child alongside
``trending`` / ``research``.
"""

from chirp.pages.types import RouteMeta

META = RouteMeta(title="Favorites", breadcrumb_label="Favorites")
