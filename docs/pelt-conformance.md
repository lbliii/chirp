# Pelt protocol conformance

Status: live result-format and dynamic-type coverage completed by issue #695;
broader extraction conformance remains in progress under issue #260.

This map separates Pelt behavior proven against a live PostgreSQL server from
sans-I/O protocol/unit proof and work that remains missing. A unit wire vector is
valuable, but it is not a substitute for server negotiation and round trips.

## Evidence matrix

| Area | Live PostgreSQL proof | Sans-I/O or unit proof | Status |
| --- | --- | --- | --- |
| Authentication | Every `test-postgres` lane connects with a password | `tests/test_pelt/test_auth.py`, `tests/test_pelt/test_transport_handshake.py` | Live password handshake covered; dedicated TLS/channel-binding matrix remains open |
| Prepared statements | `test_parallel_checkouts_keep_statement_caches_single_owner` and `test_live_extended_query_negotiates_dynamic_types_and_text_fallback` prove cache reuse with per-execution formats | `tests/test_pelt/test_protocol_extended.py` locks mixed `Bind` result codes | Covered |
| Leaf codecs | `test_live_leaf_codec_matrix` covers text results; the dynamic-type test covers mixed text/binary results | Per-family `tests/test_pelt/test_codecs*.py` modules | Covered for simple-query text and extended-query negotiated formats |
| Arrays and ranges | `test_live_array_and_range_types_preserve_text_when_binary_is_not_requested` proves simple-query text; the dynamic-type test proves binary enum arrays and a server-assigned custom range | Binary and malformed vectors in `test_codecs_array.py`, `test_codecs_composite_range_enum.py`, `test_codec_plan.py`, and `test_type_discovery.py` | Covered |
| Enums and composites | `test_live_extended_query_negotiates_dynamic_types_and_text_fallback` discovers live enum/composite OIDs and decodes a mixed result | Catalog grouping, dependency order, format selection, and malformed metadata in `test_type_discovery.py` | Covered |
| Interval output styles | `test_live_binary_interval_is_independent_of_interval_style` runs `sql_standard`, `postgres`, `postgres_verbose`, and `iso_8601` | Binary vectors in `test_codecs_temporal.py` | Covered through negotiated binary results |
| Server cursors | `test_database_executemany_and_stream` | Portal suspension/resume vectors in `test_protocol_extended.py` | Covered |
| Transactions and pool reset | `test_database_fetch_execute_transaction` and `test_pool_rolls_back_failed_transaction_before_reuse` | Connection/protocol state tests | Covered |
| LISTEN/NOTIFY | `test_listen_notify_delivery_unsubscribe_and_close` covers delivery, ordinary queries on a listening connection, multi-channel unsubscribe, and close | Notification framing and protocol events | Covered |

The live tests run through `tests/test_pelt/test_connection_integration.py` with
`CHIRP_TEST_PG_DSN`. CI's `test-postgres` matrix is the authoritative receipt;
local runs without a DSN skip these cases rather than simulating success.

## Honest boundaries

- The simple-query protocol has no `Bind` format negotiation and therefore keeps
  PostgreSQL text results. Extended/parameterized queries and server cursors send
  one explicit format code per result column.
- Registered numeric, boolean, temporal (including `INTERVAL`), UUID, bytea,
  JSON/JSONB, array, range, and composite codecs request binary. Text-like leaf
  codecs and scalar enums prefer text because their binary representation adds no
  value over UTF-8.
- A connection discovers unresolved enum, true-array, range, and composite OIDs
  from schema-qualified `pg_catalog` reads, resolves their codec dependencies,
  and remembers both hits and misses for that connection lifecycle. Unknown base,
  domain, pseudo, and multirange types remain faithful text strings.
- Statement-level `Describe` format codes remain zero, as PostgreSQL requires.
  Pelt copies that immutable declaration into a per-execution description carrying
  the exact `Bind` codes, including across portal resume. Runtime negotiation never
  mutates the prepared-statement cache entry.
- An unregistered OID is never deliberately requested in binary. If a backend or
  future negotiation bug nevertheless supplies unknown binary bytes, decoding
  raises an actionable `PELT_PROTO_DESYNC` instead of returning ambiguous bytes.
- Dynamic range and interval wrappers are frozen Pelt values behind the private
  `data-pg` seam. Their exact import location remains provisional until Pelt's
  extraction contract is complete.
- A listening connection still has exactly one socket reader. Ordinary query,
  LISTEN, and UNLISTEN round trips temporarily take exclusive read ownership;
  the notification reader resumes afterward while subscriptions remain.

PostgreSQL's protocol reference defines the `Bind` result-format count and codes,
and notes that statement-level `Describe` always reports format zero:
<https://www.postgresql.org/docs/current/protocol-message-formats.html>. Dynamic
family discovery follows `pg_type`, `pg_attribute`, and `pg_range`:
<https://www.postgresql.org/docs/current/catalog-pg-type.html> and
<https://www.postgresql.org/docs/current/catalog-pg-range.html>.
