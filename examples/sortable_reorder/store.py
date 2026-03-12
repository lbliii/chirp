"""In-memory store for sortable_reorder example.

Uses threading.Lock for free-threading safety when concurrent POSTs
(add/update/reorder) can race.
"""

import threading

_items: list[str] = ["First", "Second", "Third", "Fourth", "Fifth"]
_lock = threading.Lock()


def get_items() -> list[str]:
    with _lock:
        return _items.copy()


def add_item(name: str) -> None:
    global _items
    with _lock:
        _items = [*_items, name]


def reorder_items(from_idx: int, to_idx: int) -> None:
    global _items
    with _lock:
        if from_idx == to_idx or from_idx < 0 or to_idx < 0:
            return
        n = len(_items)
        if from_idx >= n or to_idx >= n:
            return
        item = _items[from_idx]
        new_list = list(_items)
        new_list.pop(from_idx)
        new_list.insert(to_idx, item)
        _items = new_list
