"""E1.7 (#270) — codec round-trips + the lock-guarded, fail-loud OID registry."""

import pytest
from hypothesis import given
from hypothesis import strategies as st

from chirp.data.drivers._pelt._codecs import (
    DEFAULT_REGISTRY,
    OID_BOOL,
    OID_FLOAT8,
    OID_INT4,
    OID_INT8,
    OID_TEXT,
    CodecRegistry,
    _int_codec,
    build_default_registry,
)


@pytest.mark.issue(270)
@given(value=st.integers(min_value=-(2**31), max_value=2**31 - 1))
def test_int4_round_trip(value):
    codec = DEFAULT_REGISTRY.get(OID_INT4)
    assert codec is not None
    assert codec.decode_binary(codec.encode_binary(value)) == value
    assert codec.decode_text(codec.encode_text(value)) == value


@pytest.mark.issue(270)
@given(value=st.integers(min_value=-(2**63), max_value=2**63 - 1))
def test_int8_round_trip(value):
    codec = DEFAULT_REGISTRY.get(OID_INT8)
    assert codec is not None
    assert codec.decode_binary(codec.encode_binary(value)) == value


@pytest.mark.issue(270)
@given(value=st.text())
def test_text_round_trip(value):
    codec = DEFAULT_REGISTRY.get(OID_TEXT)
    assert codec is not None
    assert codec.decode_binary(codec.encode_binary(value)) == value


@pytest.mark.issue(270)
@pytest.mark.parametrize("value", [True, False])
def test_bool_round_trip(value):
    codec = DEFAULT_REGISTRY.get(OID_BOOL)
    assert codec is not None
    assert codec.decode_binary(codec.encode_binary(value)) is value
    assert codec.decode_text(codec.encode_text(value)) is value


@pytest.mark.issue(270)
@given(value=st.floats(allow_nan=False))
def test_float8_round_trip(value):
    codec = DEFAULT_REGISTRY.get(OID_FLOAT8)
    assert codec is not None
    assert codec.decode_binary(codec.encode_binary(value)) == value


@pytest.mark.issue(270)
def test_registry_rejects_conflicting_codec():
    reg = build_default_registry()
    with pytest.raises(ValueError, match="conflicting codec"):
        reg.register(_int_codec(OID_INT4, "int4-impostor", 4))


@pytest.mark.issue(270)
def test_registry_same_codec_reregistration_is_noop():
    reg = CodecRegistry()
    codec = _int_codec(OID_INT4, "int4", 4)
    reg.register(codec)
    reg.register(codec)  # identical instance → tolerated
    assert reg.get(OID_INT4) is codec


@pytest.mark.issue(270)
def test_snapshot_is_an_immutable_view():
    snap = DEFAULT_REGISTRY.snapshot()
    assert OID_INT4 in snap
    with pytest.raises(TypeError, match="item assignment"):
        snap[999] = None
