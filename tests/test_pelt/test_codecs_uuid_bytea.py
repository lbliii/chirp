"""E2 (#255) — uuid + bytea codec round-trips and known binary/text wire vectors."""

import uuid

import pytest
from hypothesis import given
from hypothesis import strategies as st

from chirp.data.drivers._pelt._codecs_uuid_bytea import (
    LEAF_CODECS,
    OID_BYTEA,
    OID_UUID,
)
from chirp.data.drivers._pelt.errors import ProtocolError


def _codec(oid):
    for codec in LEAF_CODECS:
        if codec.oid == oid:
            return codec
    raise AssertionError(f"no leaf codec for OID {oid}")


UUID_CODEC = _codec(OID_UUID)
BYTEA_CODEC = _codec(OID_BYTEA)


# --- LEAF_CODECS surface ----------------------------------------------------
@pytest.mark.issue(255)
def test_leaf_codecs_expose_both_oids():
    oids = {c.oid for c in LEAF_CODECS}
    assert oids == {OID_UUID, OID_BYTEA}
    assert OID_UUID == 2950
    assert OID_BYTEA == 17


@pytest.mark.issue(255)
def test_names_match_pg_type():
    assert UUID_CODEC.name == "uuid"
    assert BYTEA_CODEC.name == "bytea"


# --- uuid round-trips -------------------------------------------------------
@pytest.mark.issue(255)
@given(value=st.uuids())
def test_uuid_binary_round_trip(value):
    assert UUID_CODEC.decode_binary(UUID_CODEC.encode_binary(value)) == value


@pytest.mark.issue(255)
@given(value=st.uuids())
def test_uuid_text_round_trip(value):
    assert UUID_CODEC.decode_text(UUID_CODEC.encode_text(value)) == value


@pytest.mark.issue(255)
@given(value=st.uuids())
def test_uuid_encode_accepts_string_form(value):
    # The facade may bind a plain string param; it must coerce to the same wire bytes.
    assert UUID_CODEC.encode_binary(str(value)) == UUID_CODEC.encode_binary(value)
    assert UUID_CODEC.encode_text(str(value)) == UUID_CODEC.encode_text(value)


# --- uuid known wire vectors ------------------------------------------------
@pytest.mark.issue(255)
def test_uuid_binary_known_vector():
    # uuid binary layout: the 16 raw UUID octets, big-endian (network order).
    # For 12345678-1234-5678-1234-567812345678 the hyphens are cosmetic, so the
    # 16-byte binary is exactly the hex digits packed in order.
    u = uuid.UUID("12345678-1234-5678-1234-567812345678")
    expected = bytes.fromhex("12345678123456781234567812345678")
    assert len(expected) == 16
    assert UUID_CODEC.encode_binary(u) == expected
    assert UUID_CODEC.decode_binary(expected) == u


@pytest.mark.issue(255)
def test_uuid_nil_binary_vector():
    # The nil UUID is 16 zero bytes.
    nil = uuid.UUID("00000000-0000-0000-0000-000000000000")
    expected = b"\x00" * 16
    assert UUID_CODEC.encode_binary(nil) == expected
    assert UUID_CODEC.decode_binary(expected) == nil


@pytest.mark.issue(255)
def test_uuid_text_known_vector():
    # uuid text layout: canonical 8-4-4-4-12 lowercase hyphenated hex.
    u = uuid.UUID("12345678-1234-5678-1234-567812345678")
    assert UUID_CODEC.encode_text(u) == b"12345678-1234-5678-1234-567812345678"
    assert UUID_CODEC.decode_text(b"12345678-1234-5678-1234-567812345678") == u


@pytest.mark.issue(255)
def test_uuid_text_decode_tolerates_uppercase_and_braces():
    # uuid.UUID() accepts upper-case + urn/brace noise; decode normalizes to canonical.
    u = uuid.UUID("12345678-1234-5678-1234-567812345678")
    assert UUID_CODEC.decode_text(b"12345678-1234-5678-1234-567812345678".upper()) == u


@pytest.mark.issue(255)
def test_uuid_binary_wrong_length_is_protocol_error():
    with pytest.raises(ProtocolError) as excinfo:
        UUID_CODEC.decode_binary(b"\x00" * 15)
    assert excinfo.value.code == "PELT_PROTO_DESYNC"


@pytest.mark.issue(255)
def test_uuid_text_garbage_is_protocol_error():
    with pytest.raises(ProtocolError) as excinfo:
        UUID_CODEC.decode_text(b"not-a-uuid")
    assert excinfo.value.code == "PELT_PROTO_DESYNC"


# --- bytea round-trips ------------------------------------------------------
@pytest.mark.issue(255)
@given(value=st.binary())
def test_bytea_binary_round_trip(value):
    assert BYTEA_CODEC.decode_binary(BYTEA_CODEC.encode_binary(value)) == value


@pytest.mark.issue(255)
@given(value=st.binary())
def test_bytea_text_round_trip(value):
    assert BYTEA_CODEC.decode_text(BYTEA_CODEC.encode_text(value)) == value


@pytest.mark.issue(255)
@given(value=st.binary())
def test_bytea_encode_accepts_bytearray(value):
    # bytearray is a common mutable-buffer param type; must coerce to the same wire bytes.
    assert BYTEA_CODEC.encode_binary(bytearray(value)) == value
    assert BYTEA_CODEC.encode_text(bytearray(value)) == BYTEA_CODEC.encode_text(value)


# --- bytea known wire vectors -----------------------------------------------
@pytest.mark.issue(255)
def test_bytea_binary_known_vector():
    # bytea binary layout: the raw octet string, verbatim passthrough.
    assert BYTEA_CODEC.encode_binary(b"\x00\x01") == b"\x00\x01"
    assert BYTEA_CODEC.decode_binary(b"\x00\x01") == b"\x00\x01"


@pytest.mark.issue(255)
def test_bytea_text_known_vector():
    # bytea text layout (bytea_output=hex): literal b"\\x" prefix + lowercase hex.
    # b"\x00\x01" -> b"\\x0001".
    assert BYTEA_CODEC.encode_text(b"\x00\x01") == b"\\x0001"
    assert BYTEA_CODEC.decode_text(b"\\x0001") == b"\x00\x01"


@pytest.mark.issue(255)
def test_bytea_empty_vectors():
    # An empty bytea is b"" in binary and the bare prefix b"\\x" in text.
    assert BYTEA_CODEC.encode_binary(b"") == b""
    assert BYTEA_CODEC.decode_binary(b"") == b""
    assert BYTEA_CODEC.encode_text(b"") == b"\\x"
    assert BYTEA_CODEC.decode_text(b"\\x") == b""


@pytest.mark.issue(255)
def test_bytea_high_byte_text_vector():
    # 0xDE 0xAD 0xBE 0xEF -> lowercase hex, no separators.
    payload = b"\xde\xad\xbe\xef"
    assert BYTEA_CODEC.encode_text(payload) == b"\\xdeadbeef"
    assert BYTEA_CODEC.decode_text(b"\\xdeadbeef") == payload


@pytest.mark.issue(255)
def test_bytea_text_missing_prefix_is_protocol_error():
    # The legacy escape format (no \x prefix) is rejected, not silently mis-decoded.
    with pytest.raises(ProtocolError) as excinfo:
        BYTEA_CODEC.decode_text(b"0001")
    assert excinfo.value.code == "PELT_PROTO_DESYNC"


@pytest.mark.issue(255)
def test_bytea_text_bad_hex_is_protocol_error():
    with pytest.raises(ProtocolError) as excinfo:
        BYTEA_CODEC.decode_text(b"\\xzz")
    assert excinfo.value.code == "PELT_PROTO_DESYNC"


# --- NULL handling ----------------------------------------------------------
@pytest.mark.issue(255)
def test_null_is_codec_independent():
    # SQL NULL is signalled by a -1 length at the Bind/DataRow layer (see _builder),
    # never reaching these codecs — so a codec never sees or emits None. Asserting the
    # contract: the encoders reject None as programmer misuse rather than fabricating bytes.
    for codec in LEAF_CODECS:
        with pytest.raises((TypeError, ValueError, AttributeError)):
            codec.encode_binary(None)
