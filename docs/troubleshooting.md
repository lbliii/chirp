# Pelt troubleshooting

This catalog covers stable error codes emitted by Chirp's in-tree pelt
PostgreSQL driver. Pelt is currently an internal `data-pg` implementation detail,
not part of the stable `from chirp import ...` API. Install the PostgreSQL
backend with:

```bash
pip install "bengal-chirp[data-pg]"
```

Every `PeltError` carries a `code`, an optional server/driver `hint`, and a
`doc` anchor into this page. Preserve the code in logs and support reports; do
not parse the human message.

## PELT_E_UNKNOWN

The driver raised a pelt error without a more specific category. Record the
exception type, operation, and chained exception. If a narrower subclass should
have been used, report the path that produced the generic error.

## PELT_CONN_FAILED

Pelt could not open a TCP/Unix connection, or an established connection was
lost. Verify the host, port, Unix socket, database name, network reachability,
and PostgreSQL availability. Retain the chained `OSError` for the concrete
failure reason.

## PELT_TIMEOUT

A pool checkout, connection attempt, or query exceeded its configured deadline.
Check pool saturation and database latency before increasing the timeout. A
longer deadline does not fix a leaked checkout or blocked transaction.

## PELT_PROTO_DESYNC

The backend sent a message pelt could not parse or the wire stream lost framing.
The affected connection is unsafe and is discarded. Record the PostgreSQL
version, operation, and preceding driver error; do not return that connection to
the pool.

## PELT_AUTH_FAILED

PostgreSQL authentication failed or requested an unsupported method. Verify the
username, password, `pg_hba.conf` rule, and server authentication method. Do not
log credentials or full connection strings.

## PELT_TLS_FAILED

TLS negotiation failed or the server refused encryption required by the chosen
SSL mode. Verify the server TLS configuration, CA/certificate paths, hostname,
and requested SSL mode. Do not work around certificate failures by silently
weakening production verification.

## PELT_PG_ERROR

The server returned a PostgreSQL `ErrorResponse` without a usable SQLSTATE.
Record the server severity, detail, and hint fields when present. A normal
server error with a five-character SQLSTATE uses the category below.

<a id="pelt_pg_sqlstate"></a>

## PELT_PG_SQLSTATE

The server rejected an operation and supplied a five-character SQLSTATE. The
runtime code preserves it as `PELT_PG_<SQLSTATE>`—for example,
`PELT_PG_42P01` for an undefined table. Use PostgreSQL's SQLSTATE reference to
interpret the suffix, then follow the structured `detail` and `hint` carried by
`PostgresError` when available.

Treat SQLSTATE class `08` as a connection failure, class `22` as invalid data,
class `23` as an integrity constraint violation, class `40` as a transaction
rollback/retry decision, and class `42` as a syntax or access-rule problem.
Retry only when the specific operation and SQLSTATE are known to be safe.
