# Chirp CLI Compatibility Contract

**Status:** Milo 0.4.1 migration implemented; agent exposure remains deny-by-default<br>
**Chirp issue:** [#571](https://github.com/lbliii/chirp/issues/571)<br>
**Migration issue:** [#572](https://github.com/lbliii/chirp/issues/572)<br>
**Milo partner issue:** [milo-cli#75](https://github.com/lbliii/milo-cli/issues/75)

This document began as the pre-Milo `argparse` baseline. Issue #572 moved parser
ownership to Milo's public `CLI.lazy_command()` contract while keeping the
packaged entry point and Chirp-owned handlers. The black-box suite protects
command discovery, arguments, defaults, output channels, exit codes, structured
output, warning policy, resolution failures, and lazy imports. A separate
schema-parity suite prevents the precomputed lazy schemas from drifting away
from the typed adapters.

## Invariants

- `pyproject.toml` continues to install `chirp = "chirp.cli:main"`.
- Legacy command names, arguments, defaults, output channels, exit policy, and
  lazy-import boundaries remain compatible. Milo's help presentation and
  framework root options are documented additive behavior.
- Chirp owns app resolution, `AppConfig`, server startup, hypermedia checks,
  freezing, schema operations, scaffold content, and every generated file.
- Milo may own generic command registration, parsing, help, schemas, completion,
  and explicitly selected structured execution only through public APIs.
- CLI registration never automatically exposes a command through MCP. Agent
  exposure is explicit and deny-by-default, especially for filesystem writes,
  servers, migrations, and production mutations.
- Human terminal text and machine JSON are separate contracts. An adapter must
  not scrape terminal prose to manufacture structured results.

## Root behavior

| Invocation | stdout | stderr | Exit | Contract |
| --- | --- | --- | --- | --- |
| `chirp` | Milo root help | Empty | `0` | No command is a successful help request. |
| `chirp -h`, `chirp --help` | Milo root help | Empty | `0` | Command order and summaries are stable; framework root options follow them. |
| `chirp -V`, `chirp --version` | Chirp, Kida, Bengal Pounce, and Python versions | Empty | `0` | Dependency lookup stays lazy until invoked. |
| Parse failure or unknown option | Empty | `usage:` plus `error:` | `2` | Parser-owned failure; handler is not imported. |

The legacy aliases `-h`/`--help` and `-V`/`--version` remain. There are no
command aliases or nested commands. Milo adds its standard root operations
(`--llms-txt`, `--mcp`, gateway registration, completions, verbosity, quiet,
dry-run, output-file, and force) plus per-command `--format`. All eleven Chirp
commands are currently `surfaces=("cli",)`, so MCP and llms.txt expose none of
them until a separate safety and structured-result review opts them in. In
this migration those extra output/protocol flags are reserved framework syntax:
Chirp's existing handlers still own terminal writes and side effects, so #573
must integrate structured results before those controls can govern a command.

## Command, argument, and exposure inventory

Defaults shown as `config` are resolved from the imported app after parsing.
`false` means the flag is absent. Every positional shown without a default is
required.

| Command | Positionals and options | Defaults / interactions | Current exposure class |
| --- | --- | --- | --- |
| `new` | `name`; `--minimal`, `--stream`, `--sse`, `--shell`, `--ai`, `--with-chirpui` | Flags default `false`. If several modes are supplied, source precedence is minimal → AI → stream → SSE → shell → default. `--with-chirpui` is an independent hard requirement. | Human-only; intentionally not agent-exposed because it writes a project tree. |
| `run` | `app`; `--host`, `--port`, `--production`, `--workers`, `--metrics`, `--rate-limit`, `--queue`, `--sentry-dsn` | Scalar overrides default to `None` then app config. Boolean capabilities OR with app config. Production is selected by `--production` or `debug=False`. | Human-only persistent process; intentionally not agent-exposed. |
| `dev` | Same parser surface as `run` | Also forces `debug=True` and `dev_browser_reload=True`. Other resolution matches `run`. | Human-only persistent process; intentionally not agent-exposed. |
| `check` | `app`; `--warnings-as-errors`, `--coverage`, `--deploy`, `--json`, `--baseline PATH`, `--include-info` | Flags default `false`, baseline `None`. `--deploy` implies strict warnings. `--include-info` affects structured modes. | CLI-only today. `--json` is the leading candidate for a later read-only agent projection. |
| `diff` | `app`; required `--base REF`; `--json`, `--warnings-as-errors`, `--deploy`, `--include-info` | Flags default `false`. `--deploy` implies strict warnings. | CLI-only today. `--json` is a candidate for later structured exposure after repository/auth policy review. |
| `routes` | `app` | No options beyond help. Freezes the app before printing. | Human-only today; intentionally not agent-exposed until a structured schema exists. |
| `security-check` | `app` | No options beyond help. | Human-only today; security findings need a stable structured schema before exposure. |
| `freeze` | `app`, `output`; `--exclude PREFIX [PREFIX ...]` | `exclude=None`; one or more values when present. | Human-only; intentionally not agent-exposed because it writes an output tree. |
| `makemigrations` | required `--db`, required `--schema`; `--migrations-dir` | Migrations directory defaults to `migrations`. | Human-only; intentionally not agent-exposed because it inspects a database and writes migration files. |
| `migrate` | required `--db`; `--migrations-dir` | Migrations directory defaults to `migrations`. | Human-only deploy mutation; intentionally not agent-exposed. |
| `shapes-codegen` | optional `path`; `--dry-run`, `--audit`, `--migrations DIR` | Path defaults to `.`. Default behavior is already dry-run; the flag is compatibility syntax. `--migrations` defaults to `migrations` and is reserved. Under `--audit`, path is an app import string. | Human-only today. Audit needs structured output before agent exposure. |

## App resolution and environment ownership

`run`, `dev`, `check`, `diff`, `routes`, `security-check`, `freeze`, and
`shapes-codegen --audit` accept `module[:attribute]`. Missing attributes default
to `app`; a non-`App` callable is invoked as a factory. Module, attribute,
factory, and type failures normally become `Error: …` on stderr and exit `1`.
`security-check` is the current exception: its resolver failure is uncaught, so
Python writes a traceback to stderr and exits `1`. The subprocess suite freezes
that fact without endorsing it; normalizing it requires a separate behavior
change before or after parser migration.

Environment behavior remains handler-owned:

- Imported applications may resolve any `CHIRP_*` variables through
  `AppConfig.from_env()` or their own factory. The parser does not duplicate
  those fields.
- `run` honors `CHIRP_TRACEBACK=full` for a recognized startup failure.
- `diff` sets `CHIRP_SKIP_CONTRACT_CHECKS=1` only when the caller did not
  already set it.
- `new` writes applications that later read `CHIRP_SECRET_KEY`; that variable
  does not configure the `new` parser itself.
- `makemigrations` and `migrate` consume the explicit `--db` value. Shell
  expansion such as `--db "$DATABASE_URL"` occurs before Chirp runs.

## Output channels and exit policy

| Command | Success | Expected failure |
| --- | --- | --- |
| `new` | Progress and next steps on stdout; exit `0` | Existing directory or missing required ChirpUI on stderr; exit `1` |
| `run`, `dev` | Long-running server; clean interrupt returns `0` | App resolution or formatted startup error on stderr; exit `1` |
| `check` | Human report or JSON on stdout; exit `0` | Contract errors, strict warnings, or added baseline failures exit `1`; resolution text uses stderr |
| `diff` | Human report or JSON on stdout; exit `0` | Added errors, strict added warnings, or resolution failure exit `1` |
| `routes` | Fixed-width table on stdout; exit `0` | Resolution or missing router on stderr; exit `1` |
| `security-check` | Checklist and totals on stdout; explicit exit `0` | Failed checklist remains on stdout; exit `1`. Resolution errors currently traceback on stderr. |
| `freeze` | Summary on stdout; exit `0` | Partial summary on stdout, individual render errors on stderr; exit `1` |
| `makemigrations` | No-change or generated SQL summary on stdout; exit `0` | Missing/empty schema currently prints on stdout; exit `1` |
| `migrate` | Migration summary on stdout; exit `0` | Migration failure currently prints on stdout; exit `1` |
| `shapes-codegen` | Suggestions/audit on stdout; exit `0` | Resolution or drift text currently prints on stdout; exit `1` |

Uncaught programmer errors are not normalized into a new compatibility promise.
Any future cleanup of a legacy stdout failure channel is a separately reviewed
behavior change, not part of parser migration.

## Lazy import and free-threading boundary

Importing `chirp.cli`, rendering root/subcommand help, and reporting parse
errors do not import command handlers. `_new`, `_run`, `_check`, `_diff`,
`_routes`, `_security_check`, `_freeze`, `_makemigrations`, `_migrate`, and
`_shapes_codegen` load only after their command is selected. `_version` loads
only for `-V`/`--version`.

The Milo registry and parser are built inside each `main()` call, so concurrent
callers do not share parser state. Registration uses fresh precomputed schema
dicts and lazy import paths. `tests/cli/test_milo_cli_adoption.py` compares every
precomputed schema with `function_to_schema()` on its typed adapter and builds
parsers concurrently under `PYTHON_GIL=0`.

The same-environment startup receipt on 2026-07-08 used 25 subprocesses on
CPython 3.14.2t / macOS Apple Silicon. Root `--help` measured a 70.0 ms median
on the argparse baseline and 149.5 ms after the lazy Milo migration. This is a
startup-cost receipt, not a throughput claim: Milo adds a fixed import and
registration cost, while precomputed schemas prevent command-handler imports
and reduced the initial eager-Milo prototype from 376.4 ms. No server hot path
or request benchmark changed.

## Milo public-API mapping

The migration uses released `milo-cli>=0.4.1,<0.5` and no private Milo module.
Milo issue #76 resolved the original presentation, surface-policy, lazy-error,
version-report, and terminal-rendering gaps identified by this contract.

| Chirp requirement | Milo public seam | Implemented boundary |
| --- | --- | --- |
| Command registration and typed parameters | `CLI.lazy_command()`, `Positional`, `Option`, `function_to_schema()` | Eleven typed adapters; precomputed schemas are parity-tested. |
| Deferred command imports | `LazyCommandDef` with `schema=` | Root and command help load no Chirp handler module. |
| Human output and exit ownership | `display_result=False` plus handler `SystemExit` | Existing Chirp handlers keep terminal output and exit semantics. |
| Surface policy | `surfaces=("cli",)` | No current command appears in MCP or llms.txt. |
| Version report | `version_flags` and lazy `version_report` | `-V` and `--version` retain the four-version report. |
| Positionals and legacy option spelling | `x-milo-cli` generated by typed markers | Existing argv remains valid, including `--migrations` and one-or-more `--exclude`. |
| Free-threaded parser lifecycle | Invocation-local `CLI` | No mutable registry/parser is shared across callers. |

No terminal prose is scraped into structured results. Future agent exposure
must refactor selected handlers to return domain values and belongs in a
separate reviewed issue with explicit auth, mutation, and schema policy.

## Collateral inventory

- `README.md` is a quick-start subset, not the exhaustive flag reference.
- `site/content/docs/reference/cli.md` is the user-facing command reference and
  links here for migration-grade details.
- Scaffold behavior remains owned by `src/chirp/cli/templates/`; the dependency
  is inherited through `bengal-chirp`, so generated project manifests do not
  duplicate Milo.
- Examples consume documented commands but do not register a second parser.
  Their copied invocations remain covered by the repository example and docs
  tests; #571 adds no example-only CLI behavior.
- Existing command-specific tests remain the behavioral depth layer for server
  overrides, scaffolds, checks/diffs, route tables, freeze output, migrations,
  Shapes, and app factories. The new subprocess suite is the cross-command
  compatibility layer above them.
- Deployment, database, freeze, and DevTools guides remain the narrative owners
  for their respective commands.
- `changelog.d/572.changed.md` records parser ownership, dependency range, help
  presentation, lazy behavior, and deny-by-default agent policy.
- Generated site output is intentionally not hand-edited; canonical site source
  moves with this contract.
