"""In-memory store for the recipe builder example."""

import threading
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RecipeStep:
    id: int
    instruction: str
    duration: str
    note: str = ""


_SEED_STEPS = [
    RecipeStep(1, "Preheat oven to 375°F", "5 min", "Use convection if available"),
    RecipeStep(2, "Dice onions and mince garlic", "10 min"),
    RecipeStep(3, "Sauté vegetables in olive oil", "8 min", "Medium-high heat"),
    RecipeStep(4, "Season with salt, pepper, and herbs", "2 min"),
    RecipeStep(5, "Transfer to baking dish and cover", "3 min"),
    RecipeStep(6, "Bake until golden brown", "25 min", "Check at 20 minutes"),
]

_steps: list[RecipeStep] = []
_next_id: int = 7
_lock = threading.Lock()


def reset() -> None:
    global _steps, _next_id
    with _lock:
        _steps = [RecipeStep(s.id, s.instruction, s.duration, s.note) for s in _SEED_STEPS]
        _next_id = 7


def get_steps() -> list[RecipeStep]:
    with _lock:
        return list(_steps)


def add_step(instruction: str, duration: str = "", note: str = "") -> RecipeStep:
    global _next_id
    with _lock:
        step = RecipeStep(id=_next_id, instruction=instruction, duration=duration, note=note)
        _next_id += 1
        _steps.append(step)
        return step


def remove_step(step_id: int) -> bool:
    with _lock:
        before = len(_steps)
        _steps[:] = [s for s in _steps if s.id != step_id]
        return len(_steps) < before


def reorder_steps(from_idx: int, to_idx: int) -> None:
    with _lock:
        if from_idx == to_idx or from_idx < 0 or to_idx < 0:
            return
        n = len(_steps)
        if from_idx >= n or to_idx >= n:
            return
        step = _steps[from_idx]
        new_list = list(_steps)
        new_list.pop(from_idx)
        new_list.insert(to_idx, step)
        _steps[:] = new_list


# Keep backward compat for app.py routes
def get_items() -> list[str]:
    return [s.instruction for s in get_steps()]


def add_item(name: str) -> None:
    add_step(name)


def reorder_items(from_idx: int, to_idx: int) -> None:
    reorder_steps(from_idx, to_idx)


reset()
