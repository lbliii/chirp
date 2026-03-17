# Islands + App Shell

Islands inside ChirpUI shells with htmx-boosted navigation. Demonstrates:
- Islands in `#main` with sidebar navigation
- Unmount before htmx swap, remount after
- OOB updates for breadcrumbs, title, sidebar

## Run

```bash
pip install chirp[ui]
PYTHONPATH=src python examples/chirpui/islands_shell/app.py
```

Navigate between Home, Dashboard, and About. Open the console to see
`chirp:island:mount`, `chirp:island:unmount`, and `chirp:island:remount` events.
