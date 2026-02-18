# LLM Playground — Model Comparison

Compare 2 models side-by-side with streaming responses. Built with chirp-ui — holy-light theme, empty_state, model cards with badges.

## Run

```bash
pip install chirp[ai] chirp-ui
ollama pull llama3.2    # or your preferred model
ollama serve            # in another terminal

cd examples/llm_playground && python app.py
```

Open http://127.0.0.1:8000

## Features

- **Side-by-side comparison** — 2 models stream in parallel
- **chirp-ui showcase** — holy-light theme, container, grid, model_card, streaming_block, empty_state
- **Responsive** — 2 cols desktop, 1 col mobile
- **Zero JavaScript** — htmx + SSE
- **Assets from package** — chirpui.css and themes served from chirp-ui
