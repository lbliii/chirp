"""Fail if any towncrier fragment begins with a leading ``-`` bullet.

Towncrier prepends ``-`` itself; a leading ``-`` in the fragment produces
``- -`` in the compiled CHANGELOG. See ``changelog.d/README.md``.
"""

import sys
from pathlib import Path


def main(paths: list[str]) -> int:
    bad: list[tuple[Path, str]] = []
    for raw in paths:
        path = Path(raw)
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        stripped = text.lstrip()
        if stripped.startswith(("- ", "-\t")):
            first_line = stripped.splitlines()[0] if stripped else ""
            bad.append((path, first_line))

    if not bad:
        return 0

    print("error: changelog fragments must not start with a leading '-' bullet.")
    print(
        "       towncrier prepends the bullet itself; a leading '-' produces '- -' in CHANGELOG.md."
    )
    print("       See changelog.d/README.md for format rules.")
    print()
    for path, first in bad:
        print(f"  {path}: {first[:80]}")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
