⚡ **Signals skip redundant emits.** A coalescing signal (`coalesce=True`, the
default) now skips the wire event **and** the derived cascade when its new value
equals the current one — a pure `render` maps equal values to equal payloads, so
the swap would be byte-identical. Derived signals dedup the same way: a derived
whose projection is unchanged (even when its source value changed) no longer
re-emits or propagates. This makes the *compute-once / broadcast-many* dashboard
pattern cheap — only regions that actually changed hit the wire. Append-style /
drop-sensitive topics opt out with `coalesce=False` (every emit fires, even a
repeat value).
