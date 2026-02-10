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

    Args:
        import_string: Dotted module path with optional ``:attribute``
            suffix (e.g. ``"myapp:app"``, ``"myapp.main:application"``).

    Returns:
        The resolved chirp ``App`` instance.

    Raises:
        ModuleNotFoundError: If the module cannot be imported.
        AttributeError: If the attribute does not exist on the module.
        TypeError: If the resolved object is not a chirp ``App``.

    """
    module_path, _, attr_name = import_string.partition(":")
    if not attr_name:
        attr_name = "app"

    module = importlib.import_module(module_path)
    obj = getattr(module, attr_name)

    if not isinstance(obj, App):
        msg = f"{import_string!r} resolved to {type(obj).__name__}, not a chirp.App instance"
        raise TypeError(msg)

    return obj
