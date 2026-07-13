"""E1.6 (#269) — MessageBuilder + frontend message framing."""

import pytest

from chirp.data.drivers._pelt import _builder as builder


@pytest.mark.issue(269)
def test_message_builder_joins_fields_in_order():
    mb = builder.MessageBuilder()
    mb.write_byte(ord("S"))
    mb.write_cstring("k")
    mb.write_int32(7)
    assert mb.getvalue() == b"S" + b"k\x00" + (7).to_bytes(4, "big", signed=True)


@pytest.mark.issue(269)
def test_message_builder_skips_empty_writes():
    mb = builder.MessageBuilder()
    mb.write_bytes(b"")
    mb.write_bytes(b"x")
    assert mb.getvalue() == b"x"


@pytest.mark.issue(269)
def test_frame_length_excludes_tag():
    framed = builder.frame(b"Q", b"SELECT 1\x00")
    assert framed[0:1] == b"Q"
    length = int.from_bytes(framed[1:5], "big")
    assert length == len(framed) - 1  # length counts itself but not the tag byte
    assert framed[5:] == b"SELECT 1\x00"


@pytest.mark.issue(269)
def test_frame_rejects_multibyte_tag():
    with pytest.raises(ValueError, match="one byte"):
        builder.frame(b"QQ", b"")


@pytest.mark.issue(269)
def test_build_query():
    out = builder.build_query("SELECT 1")
    assert out[0:1] == b"Q"
    assert out.endswith(b"SELECT 1\x00")
    assert int.from_bytes(out[1:5], "big") == len(out) - 1


@pytest.mark.issue(269)
def test_build_startup_is_untagged_and_carries_version():
    out = builder.build_startup(user="alice", database="shop")
    assert int.from_bytes(out[0:4], "big") == len(out)  # untagged: length is first
    assert int.from_bytes(out[4:8], "big") == builder.PROTOCOL_VERSION
    assert b"user\x00alice\x00" in out
    assert b"database\x00shop\x00" in out
    assert out.endswith(b"\x00")  # terminating empty key


@pytest.mark.issue(269)
def test_build_extended_protocol_messages_are_tagged():
    assert builder.build_parse(name="", query="SELECT $1", param_oids=(23,))[0:1] == b"P"
    assert builder.build_bind(params=[b"42", None])[0:1] == b"B"
    assert builder.build_describe(kind="P")[0:1] == b"D"
    assert builder.build_execute(max_rows=10)[0:1] == b"E"
    assert builder.build_sync() == b"S" + (4).to_bytes(4, "big")
    assert builder.build_terminate() == b"X" + (4).to_bytes(4, "big")


@pytest.mark.issue(695)
def test_build_bind_encodes_explicit_per_column_result_formats():
    body = (
        b"\x00"  # unnamed portal
        b"statement\x00"
        + (0).to_bytes(2, "big")  # text parameters
        + (0).to_bytes(2, "big")  # no parameter values
        + (3).to_bytes(2, "big")
        + (1).to_bytes(2, "big")
        + (0).to_bytes(2, "big")
        + (1).to_bytes(2, "big")
    )

    assert builder.build_bind(
        statement="statement",
        result_formats=(1, 0, 1),
    ) == builder.frame(b"B", body)
    with pytest.raises(ValueError, match=r"0 .* or 1"):
        builder.build_bind(result_formats=(2,))


@pytest.mark.issue(269)
def test_build_describe_rejects_bad_kind():
    with pytest.raises(ValueError, match="'S' or 'P'"):
        builder.build_describe(kind="X")
