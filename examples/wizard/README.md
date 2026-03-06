# Wizard

A multi-step checkout-style form flow with session-persisted progress. Each step
validates independently, forward navigation is guarded, back navigation retains
state, and confirmation clears the stored session data.

## Run

```bash
cd examples/wizard && python app.py
```

## Test

```bash
pytest examples/wizard/
```
