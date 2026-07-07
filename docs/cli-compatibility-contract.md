# Chirp CLI Compatibility Contract

**Status:** Frozen pre-Milo baseline<br>
**Chirp issue:** [#571](https://github.com/lbliii/chirp/issues/571)<br>
**Milo partner issue:** [milo-cli#75](https://github.com/lbliii/milo-cli/issues/75)

This document freezes the observable `chirp` command contract before parser
ownership can move from `argparse` to Milo. It is an inventory and migration
gate, not authorization to begin that migration. `tests/cli/test_cli_compatibility_contract.py`
executes the packaged module in subprocesses and protects command discovery,
usage, flags, output channels, exit codes, structured output, warning policy,
resolution failures, and lazy imports.

## Invariants

- `pyproject.toml` continues to install `chirp = "chirp.cli:main"`.
- No command, flag, default, output channel, exit policy, or lazy-import boundary
  changes as a side effect of changing parser libraries.
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
| `chirp` | Root help | Empty | `0` | No command is a successful help request. |
| `chirp -h`, `chirp --help` | Root help | Empty | `0` | Command order and summaries are stable. |
| `chirp -V`, `chirp --version` | Chirp, Kida, Bengal Pounce, and Python versions | Empty | `0` | Dependency lookup stays lazy until invoked. |
| Parse failure or unknown option | Empty | `usage:` plus `error:` | `2` | Parser-owned failure; handler is not imported. |

The only aliases are `-h`/`--help` and `-V`/`--version`. There are no command
aliases and no nested commands today.

## Command, argument, and exposure inventory

Defaults shown as `config` are resolved from the imported app after parsing.
`false` means the flag is absent. Every positional shown without a default is
required.

| Command | Positionals and options | Defaults / interactions | Current exposure class |
| --- | --- | --- | --- |
| `new` | `name`; `--minimal`, `--stream`, `--sse`, `--shell`, `--ai`, `--with-chirpui` | Flags default `false`. If several modes are supplied, source precedence is minimal → AI → stream → SSE → shell → default. `--with-chirpui` is an independent hard requirement. | Human-only; intentionally not agent-exposed because it writes a project tree. |
| `run` | `app`; `--host`, `--port`, `--production`, `--workers`, `--metrics`, `--rate-limit`, `--queue`, `--sentry-dsn` | Scalar overrides default to `None` then app config. Boolean capabilities OR with app config. Production is selected by `--production` or `debug=False`. | Human-only persistent process; intentionally not agent-exposed. |
| `dev` | Same parser surface as `run` | Also forces `debug=True` and `dev_browser_reload=True`. Other resolution matches `run`. | Human-only persistent process; intentionally not agent-exposed. |
| `check` | `app`; `--warnings-as-errors`, `--coverage`, `--deploy`, `--json`, `--baseline PATH`, `--include-info` | Flags default `false`, baseline `None`. `--deploy` implies strict warnings. `--include-info` affects structured modes. | Text is human-only. `--json` is structured-agent-safe read-only output. |
| `diff` | `app`; required `--base REF`; `--json`, `--warnings-as-errors`, `--deploy`, `--include-info` | Flags default `false`. `--deploy` implies strict warnings. | Text is human-only. `--json` is structured-agent-safe read-only output. |
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

The current parser is built inside each `main()` call and publishes no mutable
global registry. A Milo replacement must finish registration before dispatch,
keep registry publication immutable or lifecycle-bounded, and remain safe on
free-threaded Python. Startup/import benchmarks may be added during #572, but
this migration may not make help import application, server, data, or optional
dependency modules.

## Milo public-API mapping and gaps

The mapping below is based on Milo 0.3.1 public exports and examples at
[`1f537086`](https://github.com/lbliii/milo-cli/commit/1f5370861fa38bc7942111a623fa2cb5a7f567b9),
observed on 2026-07-06. Because
[milo-cli#75](https://github.com/lbliii/milo-cli/issues/75) is open,
presentation compatibility remains `manual-confirmation-needed` until that
upstream contract is reviewed.

| Chirp requirement | Milo public seam | Status |
| --- | --- | --- |
| Command registration and typed parameters | `CLI`, `CommandDef`, `CLI.command()`, `function_to_schema()` | Available; #572 must use thin adapter functions rather than pass `argparse.Namespace`. |
| Deferred command imports | `LazyCommandDef`, `CLI.lazy_command()` | Available in principle; machine tests must prove the same import boundary. |
| Future grouping | `Group`, `GroupDef` | Available, but Chirp has no nested command contract today. |
| Human and machine formatting | `Context`, `format_output()`, `write_output()` | Available for new structured handlers; terminal prose cannot be scraped into results. |
| Exact argparse help order, wrapping, and successful no-command behavior | `HelpRenderer` | **GAP C1:** public docs do not promise byte/exit parity with this baseline. Reproducer: the committed help-usage subprocess matrix. |
| stderr/stdout routing plus exit `0`/`1`/`2` | No reviewed typed command-outcome contract identified | **GAP C2:** upstream #75 must define framework-neutral channel and exit ownership or leave it explicitly adopter-owned. Reproducer: parse/resolution/strict-warning subprocess tests. |
| Existing JSON stdout and future typed MCP results from one execution | `InvokeResult`, `Context`, output helpers | **GAP C3:** #572 needs a public way to return structured data without double-printing and without auto-exposing the command. Reproducer: `check --json` parseability test. |
| Global `--version` with lazy adopter dependency lookup | `VersionInfo`, `check_version()` | Partial; Chirp owns its exact four-version report and lazy timing. |
| Persistent server lifecycle and `KeyboardInterrupt` | Generic command handler | Chirp-owned. Milo must not wrap, swallow, or reinterpret server lifecycle errors. |
| Filesystem/database mutation confirmation and MCP annotations | `CommandDef` annotations and `Context` | Available only after explicit policy design; all current mutating commands remain unexposed. |

Concrete gap reports belong on milo-cli#75 before #572 relies on anything
outside these public names. No required behavior may depend on Milo private
modules or argparse internals.

## Ordered migration gate for #572

1. Keep this inventory and its subprocess tests green on the argparse baseline.
2. Resolve or explicitly assign ownership for GAP C1–C3 on milo-cli#75.
3. Build private Chirp adapter functions with typed parameters and typed results;
   do not change command handlers or public output in the same step.
4. Migrate read-only structured paths first: `check --json`, `diff --json`, then
   a newly reviewed structured route/security schema if desired.
5. Migrate human-only commands behind the same black-box suite. Keep `new`,
   server, freeze, and migration behavior CLI-only.
6. Run help, exit/channel, lazy-import, free-threaded, docs, scaffold, and full
   release proof before switching the packaged entry point implementation.
7. Add MCP or agent exposure only in its own reviewed issue with explicit auth,
   confirmation, mutation, and schema policy.

## Collateral inventory

- `README.md` is a quick-start subset, not the exhaustive flag reference.
- `site/content/docs/reference/cli.md` is the user-facing command reference and
  links here for migration-grade details.
- Scaffold behavior remains owned by `src/chirp/cli/templates/` and existing
  scaffold runtime tests; no generated output changes in #571.
- Examples consume documented commands but do not register a second parser.
  Their copied invocations remain covered by the repository example and docs
  tests; #571 adds no example-only CLI behavior.
- Existing command-specific tests remain the behavioral depth layer for server
  overrides, scaffolds, checks/diffs, route tables, freeze output, migrations,
  Shapes, and app factories. The new subprocess suite is the cross-command
  compatibility layer above them.
- Deployment, database, freeze, and DevTools guides remain the narrative owners
  for their respective commands.
- `changelog.d/571.added.md` records the new compatibility artifact; release
  tooling and generated site output are unchanged.
- #571 changes no public command behavior, dependency, entry point, scaffold,
  or application API.
