"""Traceback frame extraction and framework collapsing."""

import os
import types
from typing import Any


def _is_app_frame(filename: str) -> bool:
    """True if the frame is from the application (not stdlib/site-packages)."""
    if "site-packages" in filename:
        return False
    if filename.startswith("<"):
        return False
    # stdlib check — anything inside the Python install
    stdlib_prefix = os.path.dirname(os.__file__)
    return not filename.startswith(stdlib_prefix)


def _extract_frames(tb: types.TracebackType | None) -> list[dict[str, Any]]:
    """Walk a traceback and extract frame info with source context and locals."""
    import linecache

    frames: list[dict[str, Any]] = []
    while tb is not None:
        frame = tb.tb_frame
        lineno = tb.tb_lineno
        filename = frame.f_code.co_filename
        func_name = frame.f_code.co_name

        # Source context: 5 lines before and after
        source_lines: list[tuple[int, str]] = []
        for i in range(max(1, lineno - 5), lineno + 6):
            line = linecache.getline(filename, i, frame.f_globals)
            if line:
                source_lines.append((i, line.rstrip()))

        # Locals — filter out dunder and overly large values
        local_vars: dict[str, str] = {}
        for name, value in frame.f_locals.items():
            if name.startswith("__") and name.endswith("__"):
                continue
            try:
                r = repr(value)
                if len(r) > 200:
                    r = r[:197] + "..."
                local_vars[name] = r
            except Exception:
                local_vars[name] = "<unrepresentable>"

        frames.append(
            {
                "filename": filename,
                "lineno": lineno,
                "func_name": func_name,
                "source_lines": source_lines,
                "locals": local_vars,
                "is_app": _is_app_frame(filename),
            }
        )
        tb = tb.tb_next

    return frames


def _collapse_framework_frames(
    frames: list[dict[str, Any]],
    min_collapse: int = 3,
) -> list[dict[str, Any]]:
    """Collapse consecutive non-app (framework) frames into a summary.

    Reduces traceback noise from middleware, ASGI adapters, etc.
    Returns a mix of frame dicts and collapsed-group dicts.
    """
    result: list[dict[str, Any]] = []
    i = 0
    while i < len(frames):
        frame = frames[i]
        if frame["is_app"]:
            result.append(frame)
            i += 1
            continue
        # Collect consecutive non-app frames
        run: list[dict[str, Any]] = [frame]
        i += 1
        while i < len(frames) and not frames[i]["is_app"]:
            run.append(frames[i])
            i += 1
        if len(run) >= min_collapse:
            result.append(
                {
                    "collapsed": True,
                    "count": len(run),
                    "frames": run,
                    "summary": f"{len(run)} framework frames",
                }
            )
        else:
            result.extend(run)
    return result
