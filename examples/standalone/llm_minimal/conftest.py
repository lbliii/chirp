"""llm_minimal test config — fast simulated tokens, no Ollama.

The default simulated stream pauses ``LLM_MINIMAL_DELAY`` seconds per token.
Drop it to near-zero so tests don't wait. ``USE_OLLAMA`` is read at import
time in app.py, so leaving it unset keeps tests fully offline.
"""

import os

os.environ.setdefault("LLM_MINIMAL_DELAY", "0")
