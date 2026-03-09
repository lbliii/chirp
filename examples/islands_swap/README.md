# Islands + htmx Fragment Swap

Island inside dynamically swapped content. Demonstrates:
- Island in htmx-swapped fragment
- Unmount before swap, mount after
- Reload triggers full unmount/remount cycle

## Run

```bash
cd examples/islands_swap && python app.py
```

Click "Load widget" to fetch and swap the fragment. Click "Reload" to swap again.
Open the console to see `chirp:island:mount`, `chirp:island:unmount`, and `chirp:island:remount`.
