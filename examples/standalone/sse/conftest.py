"""SSE example test config — fast delays for CI."""

import os

# Override delay so tests don't wait 1.5s per event
os.environ.setdefault("SSE_DELAY", "0.01")
