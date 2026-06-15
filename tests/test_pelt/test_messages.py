"""E1.4 (#267) — frozen wire-message dataclasses + ErrorResponse field accessors."""

from dataclasses import FrozenInstanceError

import pytest

from chirp.data.drivers._pelt._messages import (
    DataRow,
    ErrorResponse,
    FieldDescription,
    ReadyForQuery,
    RowDescription,
)


@pytest.mark.issue(267)
def test_error_response_field_accessors():
    err = ErrorResponse(
        fields=(
            ("S", "ERROR"),
            ("V", "ERROR"),
            ("C", "42P01"),
            ("M", "no such table"),
            ("D", "detail here"),
            ("H", "create it"),
        )
    )
    assert err.severity == "ERROR"
    assert err.sqlstate == "42P01"
    assert err.message_text == "no such table"
    assert err.detail == "detail here"
    assert err.hint == "create it"


@pytest.mark.issue(267)
def test_error_response_defaults_when_fields_missing():
    err = ErrorResponse(fields=())
    assert err.severity == "ERROR"
    assert err.sqlstate == "XX000"
    assert err.message_text == ""
    assert err.detail is None
    assert err.hint is None


@pytest.mark.issue(267)
def test_messages_are_frozen():
    rfq = ReadyForQuery(status="I")
    with pytest.raises(FrozenInstanceError):
        rfq.status = "T"


@pytest.mark.issue(267)
def test_row_description_and_data_row_hold_values():
    field = FieldDescription(
        name="id",
        table_oid=1,
        column_attr=1,
        type_oid=23,
        type_size=4,
        type_modifier=-1,
        format_code=0,
    )
    rd = RowDescription(fields=(field,))
    assert rd.fields[0].name == "id"
    assert rd.fields[0].type_oid == 23

    row = DataRow(values=(b"42", None))
    assert row.values == (b"42", None)
