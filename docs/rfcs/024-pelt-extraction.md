# RFC 024: Pelt standalone package and Chirp adapter

**Status:** Accepted — extraction not yet implemented

**Decision issue:** [#693](https://github.com/lbliii/chirp/issues/693)

**Parent epic:** [#260](https://github.com/lbliii/chirp/issues/260)

**Implementation issue:** [#694](https://github.com/lbliii/chirp/issues/694)

**Last audited:** 2026-07-10

**Shipping impact:** None in this RFC. It records the package, compatibility,
ownership, and adapter contracts for a later extraction. It does not create a
repository, publish a distribution, move the in-tree driver, change the
`data-pg` extra, or alter Chirp runtime behavior.

## Summary

Pelt will leave `chirp.data.drivers._pelt` and become an independently released
pure-Python PostgreSQL driver with this identity:

| Surface | Accepted name |
| --- | --- |
| Product | Pelt |
| GitHub repository | `lbliii/bengal-pelt` |
| PyPI distribution | `bengal-pelt` |
| Python import package | `bengal_pelt` |
| First publication | `0.1.0a1` prerelease |
| Required Python | `>=3.14` |

The unqualified PyPI distribution and import name `pelt` are rejected. As of
this audit, PyPI publishes an active, unrelated changepoint-detection project
under that name. The Bengal-qualified distribution and import avoid dependency
confusion and make copyable install/import instructions agree.

Chirp applications continue to use `chirp.data.Database`. The extraction does
not add a top-level Chirp export, driver-selection setting, JSON/REST side
channel, or parallel database facade. The existing `data-pg` extra becomes the
only supported way for a Chirp application to install Pelt.

## Decision inventory

| Area | Accepted decision |
| --- | --- |
| API tier | Every `bengal_pelt` 0.x top-level export is provisional. Chirp's existing `Database` and `DataError` contracts do not change tier. |
| Package/import | Distribution `bengal-pelt`; import `bengal_pelt`; repository `lbliii/bengal-pelt`. |
| Driver ownership | Pelt owns PostgreSQL wire, codecs, auth/TLS, connections, records, cursors, transactions, and pools. |
| Facade ownership | Chirp owns `Database`, configuration, retries, row-to-dataclass mapping, dialect helpers, migrations, LISTEN notification projection, and lifecycle integration. |
| Exceptions | Standalone `PeltError` no longer subclasses Chirp `DataError`; the Chirp adapter translates it at every driver boundary. |
| Optional dependency | `bengal-chirp[data-pg]` installs `bengal-pelt`; core and SQLite imports remain usable without it. |
| Compatibility | Chirp pins one compatible Pelt 0.x minor series and tests its minimum and latest releases. |
| Tests/CI | Driver conformance moves to Pelt; Chirp retains facade, adapter, absence, translation, and end-to-end integration proof. |
| Security | Pelt owns protocol/auth/TLS advisories; Chirp owns redaction, install guidance, facade translation, and coordinated disclosure at the seam. |
| Benchmarks | Driver-direct workloads move to Pelt; Chirp retains only facade/adapter overhead and application-facing regression proof. |
| Migration | The private `chirp.data.drivers._pelt` path disappears without a compatibility alias; supported applications require no code change. |
| Rollback | Revert the Chirp seam to the last in-tree implementation; never select between bundled and external drivers at runtime. |

## Standalone public surface

The first `bengal_pelt` prerelease carries the current extraction export set as
one provisional top-level API:

```python
from bengal_pelt import (
    AuthenticationError,
    Connection,
    ConnectionConfig,
    PeltConnectionError,
    PeltError,
    PeltTimeoutError,
    Pool,
    PoolConfig,
    PostgresError,
    ProtocolError,
    TLSError,
    connect,
    create_pool,
)
```

No other module path is public merely because Python can import it. In
particular, framing, messages, builders, codecs, transport, auth helpers,
runtime helpers, registries, and prepared-statement caches remain private.
`Record`, cursor, and transaction objects are returned through the public
connection methods, but their construction and concrete module paths are not
top-level API in 0.1. Their mapping, async-iteration, and async-context-manager
behavior is part of the method contract.

The provisional connection contract is the existing parameterized surface:

- `fetch(sql, /, *params)` and `fetchrow(sql, /, *params)`;
- `execute(sql, /, *params)` and `executemany(sql, params_seq, /)`;
- `cursor(sql, /, *params, prefetch=100)` and `transaction()`;
- `add_listener(...)`, `remove_listener(...)`, and `close()`; and
- pool `acquire()`, `release()`, `close()`, and read-only `size`.

Pelt continues to accept PostgreSQL `$1`, `$2`, ... placeholders. It must never
interpolate parameter values into SQL. Chirp does not translate placeholder
syntax or reinterpret command tags, records, transaction ownership, cursor
ordering, or LISTEN callbacks at the adapter boundary.

All public configuration and stable read models remain frozen and slotted.
Shared mutable registries retain their lock-and-immutable-snapshot discipline,
and no lock may span an await or network I/O. Pure Python, no libpq, and no
mandatory compiled dependency remain product invariants rather than benchmark
claims.

## Exception hierarchy and translation

Standalone Pelt owns a framework-independent tree rooted at
`PeltError(Exception)`. The current subclasses, stable `PELT_*` codes,
actionable `hint`, documentation anchor, PostgreSQL SQLSTATE metadata, and
pickle round-trip remain provisional Pelt API. `bengal-pelt` must not import
Chirp to define or raise an exception.

Chirp owns a private adapter exception that subclasses its public `DataError`.
Every Pelt call reachable through `Database` is wrapped, including pool
creation, acquire/release/close, connection query methods, transactions,
cursors, and the dedicated LISTEN connection. On `PeltError`, the adapter:

1. raises the private `DataError` subclass with the same human message;
2. copies `code`, `hint`, `doc`, and present SQLSTATE/severity/detail metadata;
3. chains the original Pelt exception with `raise ... from exc`; and
4. never copies a DSN, password, SQL parameter, or server secret into the
   wrapper message, representation, or logs.

The adapter catches `PeltError`, not `Exception` or `BaseException`. Programming
errors and cancellation therefore remain visible. Existing application code
using `except DataError` keeps working; code importing the private in-tree
`PeltError` was never supported and receives migration guidance rather than a
cross-package inheritance shim.

## Chirp adapter and optional dependency

The only external import belongs in `src/chirp/data/drivers/postgres.py` and is
lazy. `chirp`, `chirp.data`, and a SQLite-only `Database` must import and run
when `bengal-pelt` is absent.

The extraction release changes the extra to an initial compatibility window:

```toml
data-pg = ["bengal-pelt>=0.1.0a1,<0.2"]
```

If PostgreSQL is selected without the package, Chirp raises
`DriverNotInstalledError` naming both the missing distribution and the exact
repair command:

```text
PostgreSQL support requires bengal-pelt; install bengal-chirp[data-pg]
```

The import guard handles only absence of `bengal_pelt` itself. A missing
transitive module or an exception raised while importing an installed Pelt is
a broken installation and must not be mislabeled as a missing optional extra.
There is no automatic fallback to SQLite or to a bundled driver.

The adapter owns wrappers around the external pool and connection instead of
teaching every `Database` method about Pelt. `Database.listen()` must request
its dedicated connection through that adapter; it may no longer import a Pelt
pool module directly. The wrappers preserve the exact pool/connection method
shape consumed by the facade.

No `AppConfig` field, environment variable, entry-point registry, generic
driver protocol, or custom-driver hook is approved by this RFC.

## Version and release compatibility

Pelt uses PEP 440 and semantic intent while pre-1.0:

- patch releases preserve the public surface and fix behavior;
- minor releases may change provisional API with changelog and migration notes;
- the initial extraction is published as `0.1.0a1`, not as a stable release;
- Chirp selects one Pelt minor line with a lower bound and exclusive next-minor
  cap; and
- `uv.lock` records the exact artifact used for Chirp development and release.

The package resolver is the version gate. Chirp does not perform an import-time
metadata check or maintain a second compatibility table in code.

Before a Pelt release, its CI runs the latest released compatible Chirp adapter
suite against the built wheel. Before a Chirp release, CI runs the adapter and
live PostgreSQL proof against both the minimum supported Pelt and the latest
release inside the accepted minor line. Both lanes run Python 3.14 and the
free-threaded 3.14t import/stress gate where applicable.

Cross-repository CI uses released artifacts or an explicitly uploaded wheel,
never a mutable branch URL or same-author local source override. A new Pelt
minor line lands in Chirp as a normal dependency PR with migration evidence.

## Ownership after extraction

### Pelt repository

Pelt owns:

- sans-I/O messages, framing, protocol state, builders, and codecs;
- DSN parsing, auth, TLS, transport, connections, pools, cursors, transactions,
  records, LISTEN callbacks, and prepared statements;
- the Pelt exception catalog and driver troubleshooting docs;
- PostgreSQL 13-18 wire/conformance lanes;
- malformed-input fuzzing and free-threaded shared-state stress;
- source distribution and universal pure-Python wheel build/inspection; and
- driver-direct benchmark schema, harness, artifacts, and caveats.

### Chirp repository

Chirp owns:

- `Database`, `DatabaseConfig`, the `data-pg` extra, and missing-extra UX;
- SQLite/PostgreSQL URL detection and application-facing retry/lifecycle rules;
- the private pool/connection adapter and `PeltError` to `DataError`
  translation;
- row mapping, `json_path`, query/migration helpers, LISTEN `Notification`,
  jobs, and other features expressed through `Database`;
- minimum/latest cross-version adapter lanes; and
- framework docs, release notes, migration guidance, and rollback.

Neither repository owns a second copy of executable driver code after the seam
flips. Test fixtures may be duplicated only when they prove different
boundaries and name their authority.

## Test and CI move map

| Current Chirp surface | Destination after #694 |
| --- | --- |
| `src/chirp/data/drivers/_pelt/**` | `bengal-pelt/src/bengal_pelt/**` with absolute imports rewritten |
| Driver units and fuzz tests under `tests/test_pelt/**` | `bengal-pelt/tests/**` |
| Live connection/auth/TLS/codec/concurrency tests | Pelt PostgreSQL 13-18 and 3.14t CI |
| Driver-direct parts of `benchmarks/pelt.py` | Pelt benchmark package |
| `Database.stream` and application-facing benchmark proof | Chirp adapter/facade benchmark |
| Export and error-catalog tests | Pelt package/docs tests |
| Missing-extra, exception translation, facade mapping | New Chirp adapter tests |
| Schema, migration, jobs, and LISTEN through `Database` | Chirp live PostgreSQL tests |

The Chirp extraction PR must add `@pytest.mark.issue(694)` proof for the
behavioral seam. Pelt tests retain their original issue provenance in comments
or metadata where useful, but Chirp closure traceability is not imposed on the
standalone project's pytest configuration.

## Security and operational ownership

`lbliii/bengal-pelt` ships `SECURITY.md`, dependency review, secret scanning,
CodeQL where applicable, and Trusted Publishing restricted to the release
environment. Releases build from a protected tag and publish both sdist and
wheel with attestations. The wheel inspection must show pure Python and no
native extension, libpq, Chirp, or unrelated runtime dependency.

Pelt owns vulnerabilities in wire parsing, authentication, TLS, codec bounds,
connection state, and pool isolation. Chirp owns vulnerabilities in DSN/secret
redaction, optional-package loading, exception projection, facade lifecycle,
and SQL parameter forwarding. A report crossing the seam is coordinated in
both repositories; neither project closes it as "upstream" without a tracking
reference and release plan.

The repositories never print DSNs or parameters in CI receipts. Live tests use
ephemeral service credentials, and benchmark artifacts record server and
environment versions without credentials.

## Documentation and migration

Supported Chirp applications keep this code unchanged:

```python
from chirp import Database

db = Database("postgresql://...")
```

Install instructions remain `bengal-chirp[data-pg]`; they change only from
"in-tree driver" to "installs the standalone bengal-pelt driver." Chirp's
README, installation table, database guide, architecture page, troubleshooting
entry, public API notes, release notes, and `data-pg` comments move in the same
PR as the runtime seam. Canonical docs and `site/content/` must agree.

Users of the unsupported private path receive a migration note:

```python
# unsupported in-tree import
from chirp.data.drivers import _pelt

# standalone provisional driver API
import bengal_pelt
```

Chirp does not retain `chirp.data.drivers._pelt` as an alias, vendored copy, or
deprecation shim. Such a shim would eagerly or ambiguously couple core imports
to an optional package and prolong two authorities.

## Repository bootstrap and publication order

Issue #694 executes this order:

1. Create public repository `lbliii/bengal-pelt` with MIT license, README,
   contributing and security policies, code of conduct, changelog, `py.typed`,
   `src/` layout, uv lock, Ruff, ty, pytest, and Trusted Publishing workflow.
2. Move the driver, driver tests, error catalog, conformance/free-threading
   evidence, and direct benchmarks. Preserve source attribution and link the
   Chirp extraction commit in the initial changelog.
3. Rewrite imports to `bengal_pelt`, prove the accepted top-level exports, and
   prove the package has no Chirp dependency.
4. Run units, fuzzing, PostgreSQL 13-18, Python 3.14, Python 3.14t with
   `PYTHON_GIL=0`, benchmark smoke, sdist build, wheel build, and artifact
   inspection.
5. Publish `bengal-pelt==0.1.0a1` through Trusted Publishing.
6. In Chirp, add the bounded `data-pg` dependency, implement the lazy adapter,
   remove the in-tree code, update the lock, and run minimum/latest package
   lanes plus the full facade integration suite.
7. Update Chirp and Pelt docs/changelogs together, then publish the first Chirp
   release that depends on the prerelease only after its own wheel installs in
   a clean environment.

There is no git dependency, editable cross-repository source, namespace
package, or unpublished wheel in the released Chirp lock.

## Rollback

The extraction PR records the last in-tree Chirp commit and the exact Pelt
artifact hashes. If the prerelease cannot satisfy the adapter contract, revert
the Chirp extraction commits to restore the in-tree driver and empty
`data-pg` extra, then release a Chirp patch. Yank a Pelt prerelease only when it
is unusable or unsafe; do not use yanking as ordinary version selection.

Rollback never introduces runtime fallback, dual driver selection, copied
hotfixes in both repositories, or a broadened dependency cap. A fix that
belongs to Pelt lands and releases there first, followed by a bounded Chirp
dependency update.

## Rejected alternatives

- **Distribution/import `pelt`:** occupied by an unrelated active project and
  therefore unsafe and confusing.
- **Distribution `bengal-pelt`, import `pelt`:** install and import instructions
  would still collide with the existing package.
- **A `bengal.pelt` namespace:** adds namespace-package coordination without a
  user benefit and diverges from the Bengal ecosystem's import conventions.
- **Keep PeltError inheriting DataError:** forces a standalone database driver
  to depend on a web framework and creates a circular ownership boundary.
- **Bundle and install Pelt simultaneously:** creates two driver authorities,
  ambiguous exception identity, and untestable fallback behavior.
- **Expose a generic Chirp driver protocol now:** speculative public API beyond
  the extraction seam.
- **Promote Pelt 0.1 exports to stable:** the package has not yet earned an
  independent compatibility history.

## Required implementation proof for #694

- The source move is mechanically accounted for and Chirp contains no
  executable Pelt copy after extraction.
- `bengal_pelt.__all__` exactly matches this RFC and every export resolves.
- The sdist and wheel install in clean Python 3.14 and 3.14t environments; the
  wheel contains no native extension and imports with the GIL disabled.
- Pelt's sans-I/O, fuzz, PostgreSQL 13-18, auth/TLS, codec, cursor, pool,
  LISTEN, and concurrency suites pass in its repository.
- Installing Chirp without `data-pg` supports core and SQLite; selecting
  PostgreSQL fails with the exact actionable missing-extra guidance.
- Installing Chirp with `data-pg` preserves `Database` behavior, `$N`
  parameter forwarding, row mapping, transactions, streaming, LISTEN, jobs,
  migrations, and lifecycle.
- Every Pelt exception path through the facade is catchable as `DataError`,
  retains safe diagnostic metadata and chaining, and does not leak secrets.
- Chirp CI proves the minimum and latest compatible Pelt; Pelt CI proves the
  latest released compatible Chirp adapter against the built wheel.
- Driver and facade benchmark artifacts remain versioned, reproducible,
  separated by ownership, and explicitly synthetic.
- README, canonical docs, site content, public API notes, changelogs, migration
  guidance, package metadata, locks, and rollback receipt agree.

## Acceptance for this RFC

This RFC is complete when its issue-marked documentation test verifies the
package identity, public/provisional surface, exception translation,
optional-dependency failure, ownership, compatibility window, migration,
bootstrap sequence, rollback, and #694 proof inventory. No package or runtime
change is acceptance evidence for issue #693.
