# Pelt free-threading evidence

Status: implemented and continuously checked for issue #259.

Pelt's free-threading contract is ownership-based. A checked-out connection owns
its mutable protocol and prepared-statement cache. The codec registry is the one
shared mutable hot-path structure; writes take a short `threading.Lock`, and
readers decode against an immutable `MappingProxyType` snapshot. Pool reset I/O
finishes before the connection is published as available, so no pool lock is
held across network I/O.

## Evidence map

| Invariant | Implementation | Automated proof |
| --- | --- | --- |
| Runtime detects a free-threaded build with the GIL disabled and only parallelizes sufficiently large results | `src/chirp/data/drivers/_pelt/_runtime.py` | `test_should_parallelize_requires_threshold_and_nogil` |
| Parallel decode preserves row order and values | `src/chirp/data/drivers/_pelt/connection.py::_decode_rows` | `test_parallel_row_decode_matches_serial` |
| The no-GIL decode path overlaps work on multiple native threads | `ThreadPoolExecutor` branch in `_decode_rows` | `test_parallel_row_decode_overlaps_on_native_threads` checks multiple native thread IDs and elapsed time below half the serial sleep budget |
| Codec readers never observe a torn registration | `CodecRegistry.register()` and `.snapshot()` | `test_codec_registry_concurrent_writes_publish_untorn_snapshots` contends one writer with seven snapshot readers |
| A pool connection has exactly one checked-out owner | `Pool.acquire()` / `Pool.release()` | `test_pool_checkout_is_exclusive_under_task_contention` runs 64 contenders across four yielding connections |
| Reset completes before a released connection can be checked out again | `Pool.release()` awaits `reset_if_needed()` before taking the pool lock and releasing the semaphore | `test_pool_does_not_republish_connection_until_reset_finishes` |
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
- `test-postgres` runs the live integration suite against PostgreSQL 17,
  including failed-transaction recovery and concurrent per-connection cache
  reuse.

The elapsed-time test is an overlap/correctness gate, not a throughput claim.
It intentionally uses a fixed sleeping decoder to avoid runner-speed
assumptions. Production speed depends on row shapes, codecs, query latency,
hardware, and pool sizing; benchmark the real workload before drawing capacity
conclusions.
