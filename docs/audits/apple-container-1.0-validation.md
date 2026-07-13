# Apple Container 1.x validation receipt

- Issue: [#564](https://github.com/lbliii/chirp/issues/564)
- Captured: 2026-07-10
- Fixture commit: `9e54a65a3516b8589ae41b8e81a7d29a39bdb4b0`
- Fixture: `examples/chirpui/lucky_cat/Dockerfile`
- Fixture SHA-256: `420666ac4530f51f155478a4fb4db8548b84fe28a1a09f56735a3f23c52c32e8`

## Decision

**Compatible with a documented bind-address caveat.** Apple Container 1.1.0
successfully built and ran the unchanged Lucky Cat Dockerfile as a Linux ARM64
image. Health, readiness, full-page HTML, a ten-second SSE stream,
free-threading, signal forwarding, and graceful ASGI shutdown all passed.

The runtime configuration must include `CHIRP_HOST=0.0.0.0`. Without it,
`AppConfig.from_env()` uses its safe local-development default of `127.0.0.1`;
Apple Container can publish the port, but its host-to-VM forward cannot reach a
process bound only to the guest loopback interface. Railway supplies environment
hints that select `0.0.0.0` automatically, so its existing workflow is
unchanged. Generic OCI runtimes should set the already-public `CHIRP_HOST`
variable explicitly.

This validates the current stable Apple Container 1.x line on version 1.1.0,
not the literal 1.0.0 binary linked when #564 was opened. The issue's acceptance
criteria require recording the exact version used and do not require a 1.0.0
pin. No Apple-specific Dockerfile branch or framework behavior was needed.

## Captured environment

| Item | Observed value | Verification |
| --- | --- | --- |
| Hardware | MacBook Pro `Mac15,6`; Apple M3 Pro; 11 CPU cores; 36 GB RAM | `system_profiler SPHardwareDataType` |
| Host architecture | `arm64` | `uname -m` |
| macOS | 26.5.1 (`25F80`) | `sw_vers` |
| Host kernel | Darwin 25.5.0 | `uname -a` |
| Apple Container CLI/API server | 1.1.0 release, commit `5973b9c` | `container --version`; `container system version --format json` |
| Default Linux kernel bundle | Kata Containers 3.28.0 ARM64 | first-run `container system start` prompt and successful install |
| Image platform | `linux/arm64/v8`; Rosetta disabled | `container image inspect`; `container inspect` |
| Image index digest | `sha256:8c81bc816cc7542256c8f9981e02cefdf329990cd0afb9a55a55f505236503e8` | `container image inspect` |
| Image manifest digest | `sha256:d1aa490e8f18672d63f3ea98a3e7971502ebbc97395e56d5882ba5407203a1ad` | build export and `container image inspect` |

Machine identifiers, user-specific paths, generated secrets, request IDs, and
session cookies are intentionally excluded from this public receipt.

## Build proof

The committed Dockerfile was built unchanged:

```bash
container build \
  --platform linux/arm64 \
  --cpus 4 \
  --memory 4G \
  --build-arg GIT_REF=9e54a65a3516b8589ae41b8e81a7d29a39bdb4b0 \
  --tag lucky-cat:apple-container-1.1.0 \
  examples/chirpui/lucky_cat
```

The cold build completed in 50.2 seconds. Its log proves that Apple Container
handled the portability-sensitive instructions and dependencies:

- multi-stage `COPY --from=ghcr.io/astral-sh/uv:latest` completed;
- remote `ADD` fetched the pinned GitHub commit metadata;
- Debian packages installed for Linux ARM64;
- uv downloaded `cpython-3.14.6+freethreaded-linux-aarch64-gnu`;
- Chirp installed from the pinned fixture commit; and
- the OCI export produced an ARM64 manifest and index.

The base tags are mutable. At validation time the resolver selected:

```text
python:3.14-slim
  sha256:b877e50bd90de10af8d82c57a022fc2e0dc731c5320d762a27986facfc3355c1
ghcr.io/astral-sh/uv:latest
  sha256:0f36cb9361a3346885ca3677e3767016687b5a170c1a6b88465ec14aefec90aa
```

## Runtime proof

The successful run used localhost-only host publication, explicit production
configuration, a generated secret, and the deterministic simulated feed:

```bash
export CHIRP_SECRET_KEY="$(openssl rand -hex 32)"

container run \
  --detach \
  --name lucky-cat-apple-container \
  --platform linux/arm64 \
  --cpus 4 \
  --memory 2G \
  --publish 127.0.0.1:8000:8000 \
  --env PORT=8000 \
  --env CHIRP_HOST=0.0.0.0 \
  --env CHIRP_ENV=production \
  --env CHIRP_DEBUG=0 \
  --env CHIRP_LOG_FORMAT=json \
  --env CHIRP_SECRET_KEY \
  --env LUCKY_CAT_FEED=sim \
  lucky-cat:apple-container-1.1.0
```

`container inspect` reported four CPUs, 2 GiB memory, Linux ARM64 v8, Rosetta
disabled, and host `127.0.0.1:8000` forwarded to guest port 8000. A running
`container stats --no-stream` sample reported 114.92 MiB memory, seven
processes, and negligible idle CPU. These are validation settings and observed
usage, not production sizing recommendations.

### HTTP and SSE

The host-side checks produced:

| Request | Result |
| --- | --- |
| `GET /health` | 200, `text/plain`, body `ok` |
| `GET /ready` | 200, `text/plain`, body `ready` |
| `GET /` | 200, `text/html`, 80,858 bytes, full-page render intent, `<html>` and `id="markets-lobby"` present |
| `GET /ft/stream` | 200, `text/event-stream`, 13,023 bytes over 10 seconds, 10 complete SSE messages |
| `GET /ready` after SSE | 200, body `ready` |

The SSE client intentionally ended on curl's ten-second timeout. The server log
recorded the stream as a 200 response lasting 9,996.2 ms and remained ready
after the client disconnected.

### Linux ARM64 and free-threading

The proof asserted the interpreter state rather than trusting the environment
variable:

```text
$ container exec lucky-cat-apple-container python -c \
  'import platform, sys; print(platform.machine(), platform.python_version(), sys._is_gil_enabled()); assert platform.machine() in {"aarch64", "arm64"}; assert not sys._is_gil_enabled()'
aarch64 3.14.6 False
```

### Signal forwarding and graceful shutdown

```bash
container stop --signal SIGTERM --time 15 lucky-cat-apple-container
```

The command returned successfully in 0.3 seconds. `container inspect` then
reported `state: stopped`, and the application log showed the complete graceful
path before the deadline:

```text
Shutting down — draining connections...
All connections drained
Lifespan shutdown complete
Pounce server stopped
```

There was no SIGKILL escalation.

## Compatibility caveat reproduced

The first run intentionally followed the old prepared-host runbook without
`CHIRP_HOST`. Chirp started successfully but logged
`Listening on 127.0.0.1:8000`; all three host probes returned curl error 52,
`Empty reply from server`. The same image was recreated with
`CHIRP_HOST=0.0.0.0`, logged `Listening on 0.0.0.0:8000`, and passed every
probe. Both runs received SIGTERM and completed graceful lifespan shutdown.

This is expected container networking behavior, not an Apple-specific image
change. The Dockerfile remains valid for Docker/BuildKit and Railway.

## Acceptance matrix

| Check | Result | Verification status |
| --- | --- | --- |
| Record host, runtime, and image versions | Exact host, Apple Container 1.1.0, digests, and Linux ARM64 recorded | machine-verified |
| Build the committed Dockerfile | Passed unchanged with multi-stage copy, remote `ADD`, and pinned source | machine-verified |
| Run with localhost publication and production env | Passed with explicit `CHIRP_HOST=0.0.0.0` | machine-verified |
| `/health`, `/ready`, and normal HTML | All returned 200 with expected bodies/content | machine-verified |
| Long-lived SSE | Ten messages over ten seconds; post-stream readiness passed | machine-verified |
| CPython 3.14t remains GIL-disabled | `aarch64 3.14.6 False`; assertions passed | machine-verified |
| SIGTERM reaches the app and shutdown is graceful | Drain and lifespan completion logged before 15-second deadline | machine-verified |
| Record builder/container resources | Builder 4 CPU/4 GiB; runtime 4 CPU/2 GiB; sample usage recorded | machine-verified |
| Preserve Docker/BuildKit/Railway compatibility | Dockerfile unchanged; existing public env configuration used | machine-verified |
| Support decision | Compatible with documented bind-address caveat | machine-verified |

## Hosted CI viability

GitHub lists `macos-26` as an ARM64 hosted-runner image, but its hosted-runner
reference says nested virtualization is not supported on ARM64 macOS runners
because of an Apple Virtualization framework limitation. Apple Container runs
each Linux container in a lightweight virtual machine through that framework.

The resulting **inference** is that GitHub-hosted ARM64 macOS runners should not
be a required Apple Container execution surface. Keep this as a manual or
self-hosted release smoke check on a prepared Apple Silicon host. No hosted job
was executed for this receipt; revisit only if GitHub documents nested-
virtualization support or a hosted job completes this full matrix reliably.

## Primary sources

- [Apple Container 1.0 release](https://github.com/apple/container/releases/tag/1.0.0)
- [Apple Container 1.1 release](https://github.com/apple/container/releases/tag/1.1.0)
- [Apple Container README and host requirements](https://github.com/apple/container/blob/1.1.0/README.md)
- [Apple Container command reference](https://github.com/apple/container/blob/1.1.0/docs/command-reference.md)
- [Apple Container resource and port-publishing guidance](https://github.com/apple/container/blob/1.1.0/docs/how-to.md)
- [GitHub-hosted runner reference](https://docs.github.com/en/actions/reference/runners/github-hosted-runners#limitations-for-arm64-macos-runners)
- [GitHub runner image labels](https://github.com/actions/runner-images#available-images)

No changelog: this is a compatibility validation receipt. It changes no Chirp
behavior, public API, Dockerfile, support tier, or release contract.
