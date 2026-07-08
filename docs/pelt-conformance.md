# Pelt protocol conformance

Status: in progress under issue #260.

This map separates Pelt behavior proven against a live PostgreSQL server from
sans-I/O protocol/unit proof and work that remains missing. A unit wire vector is
valuable, but it is not a substitute for server negotiation and round trips.

## Evidence matrix

| Area | Live PostgreSQL proof | Sans-I/O or unit proof | Status |
| --- | --- | --- | --- |
| Authentication | Every `test-postgres` lane connects with a password | `tests/test_pelt/test_auth.py`, `tests/test_pelt/test_transport_handshake.py` | Live password handshake covered; dedicated TLS/channel-binding matrix remains open |
| Prepared statements | `test_parallel_checkouts_keep_statement_caches_single_owner` | `tests/test_pelt/test_protocol_extended.py` | Covered |
| Leaf codecs | `test_live_leaf_codec_matrix` covers integers, floats, bool, text, numeric, date/time/timestamps, UUID, bytea, JSON, and JSONB | Per-family `tests/test_pelt/test_codecs*.py` modules | Covered for the current text-result protocol |
| Arrays and ranges | `test_live_array_and_range_types_preserve_text_when_binary_is_not_requested` proves lossless text fallback | Binary vectors in `test_codecs_array.py`, `test_codecs_composite_range_enum.py`, and `test_codec_plan.py` | Text fallback covered; live binary-result negotiation remains open |
| Enums and composites | None | Binary/text primitives in `test_codecs_composite_range_enum.py` | Missing live server-assigned OID proof |
| Server cursors | `test_database_executemany_and_stream` | Portal suspension/resume vectors in `test_protocol_extended.py` | Covered |
| Transactions and pool reset | `test_database_fetch_execute_transaction` and `test_pool_rolls_back_failed_transaction_before_reuse` | Connection/protocol state tests | Covered |
| LISTEN/NOTIFY | None | Notification framing and protocol events only | Missing live lifecycle proof |

The live tests run through `tests/test_pelt/test_connection_integration.py` with
`CHIRP_TEST_PG_DSN`. CI's `test-postgres` matrix is the authoritative receipt;
local runs without a DSN skip these cases rather than simulating success.

## Honest boundaries

- Pelt currently binds parameters and requests result columns in PostgreSQL text
  format. Registered leaf codecs decode that format into typed Python values.
- Binary array/range/composite codecs have deterministic wire-vector coverage,
  but the connection does not yet request binary result formats. Live array and
  range text values therefore remain faithful strings instead of being guessed
  into Python containers; server-assigned enum/composite OIDs remain unproven.
- `INTERVAL` text decoding remains deliberately unsupported until the grammar is
  validated against live server `IntervalStyle` variants. Binary interval vectors
  are covered separately.
- A live LISTEN/NOTIFY test must prove delivery, unsubscribe, and close behavior
  without two tasks reading the same connection concurrently. Until that exists,
  the feature is not marked live-conformant here.
