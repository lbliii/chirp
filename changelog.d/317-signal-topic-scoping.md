### Added

- **Signals (#317):** `signal_connect()` now finalizes a scoped `/_chirp/live?topics=…` URL at end-of-render from runtime binding tracking, so async sources pump only for bound topics and derived dependencies. Optional proactive activation via `app.set_signal_prefix_topics({"/prefix": ("signal", …)})`.
