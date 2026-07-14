# Pelt protocol conformance

Status: live result-format and dynamic-type coverage completed by issue #695;
TLS and authentication coverage completed by issue #691; broader extraction
conformance remains in progress under issue #260.

This map separates Pelt behavior proven against a live PostgreSQL server from
sans-I/O protocol/unit proof and work that remains missing. A unit wire vector is
valuable, but it is not a substitute for server negotiation and round trips.

## Evidence matrix

| Area | Live PostgreSQL proof | Sans-I/O or unit proof | Status |
| --- | --- | --- | --- |
| Authentication | `test_live_scram_and_password_authentication` proves explicit `scram-sha-256` and `password` HBA rules; `test_live_bad_credentials_are_actionable` proves SQLSTATE `28P01` | `tests/test_pelt/test_auth.py`, `tests/test_pelt/test_transport_handshake.py` | Covered on PostgreSQL 13–18; SCRAM channel binding is explicitly excluded |
| TLS modes | `test_live_sslmode_matrix` proves `verify-full`, `verify-ca`, `require`, `prefer`, and `disable`; dedicated failures prove bad CA and hostname diagnostics | `tests/test_pelt/test_transport.py` locks SSLRequest refusal, hostname input, explicit CA loading, and cleanup | Covered on PostgreSQL 13–18 with generated one-day certificates |
| Prepared statements | `test_parallel_checkouts_keep_statement_caches_single_owner` and `test_live_extended_query_negotiates_dynamic_types_and_text_fallback` prove cache reuse with per-execution formats | `tests/test_pelt/test_protocol_extended.py` locks mixed `Bind` result codes | Covered |
| Leaf codecs | `test_live_leaf_codec_matrix` covers text results; the dynamic-type test covers mixed text/binary results | Per-family `tests/test_pelt/test_codecs*.py` modules | Covered for simple-query text and extended-query negotiated formats |
| Arrays and ranges | `test_live_array_and_range_types_preserve_text_when_binary_is_not_requested` proves simple-query text; the dynamic-type test proves binary enum arrays and a server-assigned custom range | Binary and malformed vectors in `test_codecs_array.py`, `test_codecs_composite_range_enum.py`, `test_codec_plan.py`, and `test_type_discovery.py` | Covered |
| Enums and composites | `test_live_extended_query_negotiates_dynamic_types_and_text_fallback` discovers live enum/composite OIDs and decodes a mixed result | Catalog grouping, dependency order, format selection, and malformed metadata in `test_type_discovery.py` | Covered |
| Interval output styles | `test_live_binary_interval_is_independent_of_interval_style` runs `sql_standard`, `postgres`, `postgres_verbose`, and `iso_8601` | Binary vectors in `test_codecs_temporal.py` | Covered through negotiated binary results |
| Server cursors | `test_database_executemany_and_stream` | Portal suspension/resume vectors in `test_protocol_extended.py` | Covered |
| Transactions and pool reset | `test_database_fetch_execute_transaction` and `test_pool_rolls_back_failed_transaction_before_reuse` | Connection/protocol state tests | Covered |
| LISTEN/NOTIFY | `test_listen_notify_delivery_unsubscribe_and_close` covers delivery, ordinary queries on a listening connection, multi-channel unsubscribe, and close | Notification framing and protocol events | Covered |

The live tests run through `tests/test_pelt/test_connection_integration.py` with
`CHIRP_TEST_PG_DSN` and `tests/test_pelt/test_tls_auth_integration.py` with the
dedicated TLS fixture variables. CI's `test-postgres` matrix is the
authoritative receipt; local runs without those inputs skip these cases rather
than simulating success.

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
- `verify-ca` validates the server chain against system roots or the DSN's
  `sslrootcert`; `verify-full` adds hostname verification. `require` and
  `prefer` encrypt without certificate verification, while `disable` remains
  cleartext. `prefer` falls back only when PostgreSQL refuses SSL before the
  handshake; Pelt does not reconnect after a failed TLS handshake.
- Pelt supports PostgreSQL cleartext password, MD5, and SCRAM-SHA-256 exchanges.
  SCRAM channel binding (`SCRAM-SHA-256-PLUS`) is not implemented and remains
  outside the supported boundary.
- A failed TLS negotiation or authentication closes its stream, and partial
  pool construction closes every connection that already succeeded.

PostgreSQL's protocol reference defines the `Bind` result-format count and codes,
and notes that statement-level `Describe` always reports format zero:
<https://www.postgresql.org/docs/current/protocol-message-formats.html>. Dynamic
family discovery follows `pg_type`, `pg_attribute`, and `pg_range`:
<https://www.postgresql.org/docs/current/catalog-pg-type.html> and
<https://www.postgresql.org/docs/current/catalog-pg-range.html>.
