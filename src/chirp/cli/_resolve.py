"""App import resolution — resolves ``"module:attribute"`` strings to App instances.

Shared utility used by ``chirp run`` and ``chirp check`` to locate a
chirp App from a user-supplied import string.
"""

import importlib

from chirp.app import App


def resolve_app(import_string: str) -> App:
    """Resolve an import string to a chirp App instance.

    Accepts ``"module:attribute"`` format.  When the attribute portion
    is omitted, defaults to ``"app"`` (e.g. ``"myapp"`` resolves to
    ``myapp.app``).

    Supports factory functions: if the resolved object is callable and
    not an App instance, it will be called (assuming it's an app factory).

    Args:
        import_string: Dotted module path with optional ``:attribute``
            suffix (e.g. ``"myapp:app"``, ``"myapp.main:application"``,
            ``"myapp:create_app"``).

    Returns:
        The resolved chirp ``App`` instance.

    Raises:
        ModuleNotFoundError: If the module cannot be imported.
        AttributeError: If the attribute does not exist on the module.
        TypeError: If the resolved object is not a chirp ``App`` or callable.

    """
    module_path, _, attr_name = import_string.partition(":")
    if not attr_name:
        attr_name = "app"

    module = importlib.import_module(module_path)
    obj = getattr(module, attr_name)

    # Support factory functions - call them if they're not already an App
    if callable(obj) and not isinstance(obj, App):
        try:
            obj = obj()
        except Exception as exc:
            msg = f"Factory function {import_string!r} raised an error: {exc}"
            raise TypeError(msg) from exc

    if not isinstance(obj, App):
        msg = f"{import_string!r} resolved to {type(obj).__name__}, not a chirp.App instance"
        raise TypeError(msg)

    return obj
