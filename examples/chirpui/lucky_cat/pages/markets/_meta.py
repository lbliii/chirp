"""Route metadata for Markets Home — the curated lobby at /markets (#281).

One of the five fixed Markets destinations. ``/`` is an alias rendering this same
lobby, so the breadcrumb label matches the root landing ("Markets").
"""

from chirp.pages.types import RouteMeta

META = RouteMeta(title="Markets", breadcrumb_label="Markets")
