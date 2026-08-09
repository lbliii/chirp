# Pelt free-threading evidence

Status: implemented and continuously checked for issues #259 and #260.

Stack context: the Bengal
[free-threading stack ledger](design/free-threading-stack-ledger.md)
(`docs/design/free-threading-stack-ledger.md`)
places Pelt's pool checkout and codec snapshots in the shared-vs-isolated map
alongside Chirp, Kida, and Pounce (#944).

Pelt's free-threading contract is ownership-based. A checked-out connection owns
its mutable protocol, prepared-statement cache, dynamic-type discovery ledger,
and database-specific codec registry. Registry writes take a short
`threading.Lock`, and readers decode against an immutable `MappingProxyType`
snapshot. Keeping live registries connection-local prevents server-assigned OID
metadata from one database leaking into another. The process-wide built-in
registry remains lock-guarded for module consumers and construction templates.
Pool construction acquires a process-wide immutable type-catalog cache keyed by
host/port/database (#953): the first checkout that discovers `pg_catalog` facts
publishes a warm snapshot; later checkouts hydrate connection-local codecs from
that snapshot without re-querying. Writers take a short lock only around
publish/invalidate — never across await or I/O. Pool reset I/O finishes before
the connection is published as available, so no pool lock is held across network
I/O.

## Product boundary

Pelt is currently a private, in-tree implementation behind Chirp's `data-pg`
seam. It is pure Python and speaks the PostgreSQL wire protocol without libpq,
psycopg, asyncpg, or a compiled runtime extension. Applications should use
`chirp.data.Database`, not import `chirp.data.drivers._pelt`; the seam is the
planned extraction boundary for the standalone `bengal-pelt` distribution and
`bengal_pelt` import accepted in [RFC 024](rfcs/024-pelt-extraction.md). The RFC
records a future move; the driver remains in-tree until its implementation issue
ships.

## Evidence map

| Invariant | Implementation | Automated proof |
| --- | --- | --- |
| Runtime detects a free-threaded build with the GIL disabled and only parallelizes sufficiently large results | `src/chirp/data/drivers/_pelt/_runtime.py` | `test_should_parallelize_requires_threshold_and_nogil` |
| Parallel decode preserves row order and values | `src/chirp/data/drivers/_pelt/connection.py::_decode_rows` | `test_parallel_row_decode_matches_serial` |
| The no-GIL decode path overlaps work on multiple native threads | `ThreadPoolExecutor` branch in `_decode_rows` | `test_parallel_row_decode_overlaps_on_native_threads` checks multiple native thread IDs and elapsed time below half the serial sleep budget |
| Codec readers never observe a torn registration | `CodecRegistry.register()` and `.snapshot()` | `test_codec_registry_concurrent_writes_publish_untorn_snapshots` contends one writer with seven snapshot readers |
| Server-assigned OID codecs do not cross database sessions | one fresh `CodecRegistry` and attempted-OID ledger per `Connection` | `test_dynamic_codec_registries_are_connection_local` resolves conflicting same-OID metadata in isolated registries |
| A pool connection has exactly one checked-out owner | `Pool.acquire()` / `Pool.release()` | `test_pool_checkout_is_exclusive_under_task_contention` runs 64 contenders across four yielding connections |
| Reset completes before a released connection can be checked out again | `Pool.release()` awaits `reset_if_needed()` before taking the pool lock and releasing the semaphore | `test_pool_does_not_republish_connection_until_reset_finishes` |
| Warm type-catalog metadata is shared immutably across pool checkouts | `TypeCatalogCache` / `create_pool` | `test_second_checkout_skips_redundant_catalog_queries`; `test_type_catalog_cache_concurrent_reads_are_safe` |
| A server error is drained through `ReadyForQuery` before it is raised to application code | `Connection._roundtrip()` retains the first error while consuming the exchange and publishing transaction state | `test_error_drains_ready_frame_before_rollback_and_reuse` fragments the error and ready frames, then reuses the same connection |
| Failed PostgreSQL transactions are rolled back before reuse | `Connection.reset_if_needed()` | `test_pool_rolls_back_failed_transaction_before_reuse` against PostgreSQL 17 |
| Prepared statements are computed once per checked-out connection, not shared globally | per-connection `PreparedStatementCache` | `test_parallel_checkouts_keep_statement_caches_single_owner` repeats the same query on four concurrent live connections and observes one cache entry/name per owner |

The statement cache deliberately has no shared/global lock. A cache belongs to
one protocol, a protocol belongs to one connection, and pool checkout grants one
task exclusive ownership. A global cache would couple independent server
sessions and introduce a lock into the query hot path.

## CI receipts

- `data-pg-gil-gate` runs Python 3.14t with `PYTHON_GIL=0` and
  `PYTHONWARNINGS=error`, then executes the import and concurrency stress suite.
- `test-postgres` runs the live integration suite against PostgreSQL 13–18,
  including failed-transaction recovery and concurrent per-connection cache
  reuse. PostgreSQL 13 is pinned to its final 13.22 image as an EOL
  compatibility lane; majors 14–18 track their current official images.

The elapsed-time test is an overlap/correctness gate, not a throughput claim.
It intentionally uses a fixed sleeping decoder to avoid runner-speed
assumptions. Production speed depends on row shapes, codecs, query latency,
hardware, and pool sizing; benchmark the real workload before drawing capacity
conclusions.

A pool can overlap independent operations on different checked-out connections.
One `Database.stream()` call still owns one connection and one server portal,
advances through ordered batches, and does not scale with pool size. Its decoded
buffer is bounded by `batch_size`. `Database.execute_many()` currently performs
individual executions rather than `COPY` or protocol pipelining. Those are
explicit single-query and bulk-performance boundaries until a reproducible Pelt
benchmark artifact says more.
