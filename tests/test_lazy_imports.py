"""Tests for chirp.__init__ — lazy import registry covers all public names."""


import pytest

import chirp


@pytest.mark.parametrize("name", chirp.__all__)
def test_all_names_resolve(name: str) -> None:
    """Every name in __all__ must resolve via __getattr__ without error."""
    obj = getattr(chirp, name)
    assert obj is not None, f"chirp.{name} resolved to None"


def test_all_names_in_lazy_registry() -> None:
    """Every name in __all__ has a corresponding entry in _LAZY_IMPORTS."""
    missing = set(chirp.__all__) - set(chirp._LAZY_IMPORTS)
    assert not missing, (
        f"Names in __all__ but not in _LAZY_IMPORTS: {sorted(missing)}. "
        f"Add them to _LAZY_IMPORTS in chirp/__init__.py."
    )


def test_lazy_registry_no_extras() -> None:
    """Every name in _LAZY_IMPORTS should be in __all__ (public API contract)."""
    extras = set(chirp._LAZY_IMPORTS) - set(chirp.__all__)
    assert not extras, (
        f"Names in _LAZY_IMPORTS but not in __all__: {sorted(extras)}. "
        f"Either add them to __all__ or remove from _LAZY_IMPORTS."
    )


def test_unknown_name_raises_attribute_error() -> None:
    """Accessing an unregistered name raises AttributeError."""
    with pytest.raises(AttributeError, match="no attribute"):
        chirp.__getattr__("ThisDoesNotExist")
