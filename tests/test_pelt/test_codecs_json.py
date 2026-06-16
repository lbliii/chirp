"""E2 (#255) — json/jsonb codec round-trips, known binary vectors, and fail-loud framing."""

import json

import pytest
from hypothesis import given
from hypothesis import strategies as st

from chirp.data.drivers._pelt._codecs_json import (
    LEAF_CODECS,
    OID_JSON,
    OID_JSONB,
    _json_codec,
    _jsonb_codec,
)
from chirp.data.drivers._pelt.errors import ProtocolError


def _by_oid(oid):
    for codec in LEAF_CODECS:
        if codec.oid == oid:
            return codec
    raise AssertionError(f"no leaf codec for OID {oid}")


# A recursive strategy over everything json.loads can produce. Floats are restricted to
# finite values because JSON has no NaN/Inf and round-trips must be exact equality.
_json_values = st.recursive(
    st.none()
    | st.booleans()
    | st.integers(min_value=-(2**53), max_value=2**53)
    | st.floats(allow_nan=False, allow_infinity=False)
    | st.text(),
    lambda children: st.lists(children) | st.dictionaries(st.text(), children),
    max_leaves=20,
)


# --- registry wiring --------------------------------------------------------
@pytest.mark.issue(255)
def test_leaf_codecs_expose_both_oids():
    oids = {codec.oid for codec in LEAF_CODECS}
    assert oids == {OID_JSON, OID_JSONB}


@pytest.mark.issue(255)
def test_oid_constants_match_pg_type():
    assert OID_JSON == 114
    assert OID_JSONB == 3802


# --- round-trip properties (encode -> decode == identity) -------------------
@pytest.mark.issue(255)
@given(value=_json_values)
def test_json_binary_round_trip(value):
    codec = _by_oid(OID_JSON)
    assert codec.decode_binary(codec.encode_binary(value)) == value


@pytest.mark.issue(255)
@given(value=_json_values)
def test_json_text_round_trip(value):
    codec = _by_oid(OID_JSON)
    assert codec.decode_text(codec.encode_text(value)) == value


@pytest.mark.issue(255)
@given(value=_json_values)
def test_jsonb_binary_round_trip(value):
    codec = _by_oid(OID_JSONB)
    assert codec.decode_binary(codec.encode_binary(value)) == value


@pytest.mark.issue(255)
@given(value=_json_values)
def test_jsonb_text_round_trip(value):
    codec = _by_oid(OID_JSONB)
    assert codec.decode_text(codec.encode_text(value)) == value


# --- known binary vectors ---------------------------------------------------
# json binary == verbatim UTF-8 JSON text, no envelope. _dumps emits compact JSON
# (separators=(",", ":")), so {"a": 1} encodes as '{"a":1}' — no whitespace.
@pytest.mark.issue(255)
def test_json_binary_vector_object():
    codec = _by_oid(OID_JSON)
    wire = codec.encode_binary({"a": 1})
    assert wire == b'{"a":1}'
    assert codec.decode_binary(wire) == {"a": 1}


# jsonb binary layout: [version:uint8=0x01][UTF-8 JSON text...]. The leading byte for
# {"a": 1} is 0x01 (jsonb version 1), then the same compact text body as json.
@pytest.mark.issue(255)
def test_jsonb_binary_vector_object_starts_with_version_byte():
    codec = _by_oid(OID_JSONB)
    wire = codec.encode_binary({"a": 1})
    assert wire[0] == 0x01
    assert wire == b'\x01{"a":1}'
    assert codec.decode_binary(wire) == {"a": 1}


# A scalar (number) document is valid JSON on its own; the jsonb envelope is unchanged.
@pytest.mark.issue(255)
def test_jsonb_binary_vector_scalar():
    codec = _by_oid(OID_JSONB)
    wire = codec.encode_binary(42)
    assert wire == b"\x01" + b"42"
    assert codec.decode_binary(wire) == 42


# A JSON null is the literal text b"null" — distinct from a SQL NULL column (handled one
# layer up by the DataRow framer, which never calls the codec for a -1 length).
@pytest.mark.issue(255)
def test_json_null_literal_round_trips():
    json_codec = _by_oid(OID_JSON)
    assert json_codec.encode_binary(None) == b"null"
    assert json_codec.decode_binary(b"null") is None

    jsonb_codec = _by_oid(OID_JSONB)
    assert jsonb_codec.encode_binary(None) == b"\x01null"
    assert jsonb_codec.decode_binary(b"\x01null") is None


# --- decode against a known server-shaped vector ----------------------------
# Simulates what jsonb_send would emit for ["x", true, null]: 0x01 then the text body.
@pytest.mark.issue(255)
def test_jsonb_decode_known_server_vector():
    codec = _by_oid(OID_JSONB)
    body = json.dumps(["x", True, None]).encode("utf-8")
    wire = b"\x01" + body
    assert codec.decode_binary(wire) == ["x", True, None]


# --- fail-loud framing ------------------------------------------------------
@pytest.mark.issue(255)
def test_jsonb_bad_version_byte_raises_protocol_error():
    codec = _by_oid(OID_JSONB)
    # 0x02 is not a jsonb version PostgreSQL has ever emitted.
    with pytest.raises(ProtocolError, match="unsupported jsonb version"):
        codec.decode_binary(b"\x02{}")


@pytest.mark.issue(255)
def test_jsonb_empty_payload_raises_protocol_error():
    codec = _by_oid(OID_JSONB)
    with pytest.raises(ProtocolError, match="empty jsonb payload"):
        codec.decode_binary(b"")


@pytest.mark.issue(255)
def test_json_malformed_text_raises_protocol_error():
    codec = _by_oid(OID_JSON)
    with pytest.raises(ProtocolError, match="invalid JSON payload"):
        codec.decode_binary(b"{not valid json")


@pytest.mark.issue(255)
def test_jsonb_malformed_text_after_version_raises_protocol_error():
    codec = _by_oid(OID_JSONB)
    with pytest.raises(ProtocolError, match="invalid JSON payload"):
        codec.decode_binary(b"\x01{not valid json")


@pytest.mark.issue(255)
def test_json_invalid_utf8_raises_protocol_error():
    codec = _by_oid(OID_JSON)
    with pytest.raises(ProtocolError, match="invalid JSON payload"):
        codec.decode_binary(b"\xff\xfe")


# --- registry-safe shape ----------------------------------------------------
# Codecs carry closures, so two freshly-built instances are *not* ==; the registry tolerates
# re-registering the *same* instance (identity), which is exactly what LEAF_CODECS provides.
@pytest.mark.issue(255)
def test_leaf_codec_instances_are_stable_and_self_equal():
    json_codec = _by_oid(OID_JSON)
    jsonb_codec = _by_oid(OID_JSONB)
    assert json_codec is _by_oid(OID_JSON)
    assert jsonb_codec is _by_oid(OID_JSONB)
    assert json_codec == json_codec  # frozen dataclass identity-stable equality
    assert jsonb_codec == jsonb_codec


@pytest.mark.issue(255)
def test_factories_build_independent_working_codecs():
    # Distinct instances (closures differ), but each decodes/encodes correctly.
    assert _json_codec().decode_binary(_json_codec().encode_binary([1, 2])) == [1, 2]
    assert _jsonb_codec().decode_binary(_jsonb_codec().encode_binary([1, 2])) == [1, 2]
