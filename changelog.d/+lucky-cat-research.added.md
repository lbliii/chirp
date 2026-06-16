🔬 **Lucky Cat — Research destination (`/markets/research`).** A new fixed Markets
destination and the scalable power surface for a 500+ coin catalog: substring
search (sharing the same `search.matches` matcher as the Cmd-K palette), facet
filters (sector + price / 24h-change / volume bands), sortable column headers,
**server-side pagination**, and a lightweight server-rendered compare tray. It is
URL-param-driven (`?q=&sort=&dir=&page=&sector=` + band keys + `cmp`), so every
control is a bookmarkable querystring and the whole surface is back-button-correct;
each control's `hx-get` URL is precomputed in `page.py` (the `research_url` helper)
and the filter → stable-sort → slice runs entirely server-side via the shared
`research.query_catalog` seam, so it renders only one page of rows regardless of
catalog size and its numbers / ordering match the rest of the Markets surfaces.
Every search / sort / filter / paginate / compare control self-overrides the
boosted shell's inherited outlet (`hx-target` / `hx-select` → `#research-results`)
and `page.py` re-emits that wrapper — the canonical boosted-shell local-swap
pattern (footgun #2).
