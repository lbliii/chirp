# Apple Container 1.0 validation receipt

- Issue: [#564](https://github.com/lbliii/chirp/issues/564)
- Captured: 2026-07-09
- Fixture commit: `10c4f3a386d9ed51c3402c313eb57cf717cd7567`
- Fixture: `examples/chirpui/lucky_cat/Dockerfile`
- Fixture SHA-256: `420666ac4530f51f155478a4fb4db8548b84fe28a1a09f56735a3f23c52c32e8`

## Decision

**Compatibility is unverified. Do not publish an Apple Container support
claim.** The available Apple Silicon host meets Apple's hardware and operating
system prerequisites, but Apple Container is not installed. The build, run,
HTTP, SSE, free-threading, and shutdown checks therefore did not execute.

For the support choices in #564, the current decision is **not currently
supportable on the available validation host**. This is an environment blocker,
not evidence that the image is incompatible. Documentation issue #565 must
remain blocked until the end-to-end matrix below passes on a prepared Apple
Container 1.0 host.

## Captured environment

| Item | Observed value | Verification |
| --- | --- | --- |
| Hardware | MacBook Pro `Mac15,6`; Apple M3 Pro; 11 CPU cores; 36 GB RAM | `system_profiler SPHardwareDataType` |
| Host architecture | `arm64` | `uname -m` |
| macOS | 26.5.1 (`25F80`) | `sw_vers` |
| Kernel | Darwin 25.5.0 | `uname -a` and `system_profiler SPSoftwareDataType` |
| Apple Container | Not installed; no package receipt found | `command -v container` produced no path; `container --version` exited 127; `pkgutil --pkgs` contained no matching receipt |
| Apple Container version used | None | Runtime prerequisite blocked execution |
| Image architecture used | None | No image was built or run |

Machine identifiers and user-specific fields from `system_profiler` are
intentionally excluded from this public receipt.

## Evidence completed without the runtime

The committed Dockerfile was not changed. Static inspection confirms that it
contains no Apple-specific branch and continues to use the same standard
Dockerfile surface intended for Docker/BuildKit and Railway:

- a multi-stage `COPY --from=ghcr.io/astral-sh/uv:latest`;
- `ARG GIT_REF` plus a remote `ADD` used as the cache-bust input;
- a Linux slim base with `apt-get` and Linux ARM64-capable dependencies;
- a uv-managed CPython `3.14t` environment;
- `PYTHON_GIL=0`; and
- one exec-form `CMD ["python", "app.py"]`.

Remote OCI manifest inspection succeeded without a daemon:

```text
$ docker buildx imagetools inspect python:3.14-slim
index digest: sha256:b877e50bd90de10af8d82c57a022fc2e0dc731c5320d762a27986facfc3355c1
linux/arm64/v8 manifest: sha256:8b48630e688730a22bd25f3c9e04606b37fa1488cf70e665932ef78a3ee1e4d0

$ docker buildx imagetools inspect ghcr.io/astral-sh/uv:latest
index digest: sha256:0f36cb9361a3346885ca3677e3767016687b5a170c1a6b88465ec14aefec90aa
linux/arm64 manifest: sha256:92998b3232ea0c7c63abdd688d50f66c02555db96cda207d5776c088a63dc45f
```

Those tags are mutable; the digests record what was inspected on 2026-07-09.
ARM64 manifests are necessary but do not prove that Apple Container can execute
the Dockerfile's multi-stage copy, remote `ADD`, downloads, or runtime process.

## Acceptance matrix

| Check | Result | Verification status |
| --- | --- | --- |
| Record host and runtime versions | Host recorded; runtime version unavailable | machine-verified |
| Build the committed Dockerfile | Blocked before invocation: `container` executable absent | manual-confirmation-needed |
| Run Linux ARM64 with localhost publishing and production env | Blocked | manual-confirmation-needed |
| `/health`, `/ready`, and normal HTML | Blocked in Apple Container; Lucky Cat's local test surface covers these paths | manual-confirmation-needed for Apple Container |
| Long-lived SSE | Blocked | manual-confirmation-needed |
| CPython 3.14t remains GIL-disabled | Blocked | manual-confirmation-needed |
| SIGTERM reaches the app and shutdown is graceful | Blocked | manual-confirmation-needed |
| Record actual builder/container resources | No builder or container started | manual-confirmation-needed |
| Docker/BuildKit/Railway compatibility | Dockerfile unchanged; no new compatibility claim | machine-verified source state only |

## Prepared-host runbook

These commands are copied from the Apple Container 1.0 command surface and are
**not successful results from this host**. Run them from the repository root on
a prepared host, retain their complete output, and replace this blocked receipt
with the results. Apple documents macOS 26 on Apple Silicon as the supported
host and installation through its signed package, followed by
`container system start`.

### 1. Record the runtime and start its services

```bash
uname -m
sw_vers
system_profiler SPHardwareDataType
container --version
container system start
container system status --format json
container system version --format json
```

Sanitize serial numbers, hardware UUIDs, user names, and other host identifiers
before committing captured output.

### 2. Build the unchanged fixture

Pin `GIT_REF` to the fixture commit so the build installs the same Chirp source
that supplied the Dockerfile. The explicit limits make the resource receipt
repeatable; they are proposed validation settings, not measured requirements.

```bash
container build \
  --platform linux/arm64 \
  --cpus 4 \
  --memory 4G \
  --build-arg GIT_REF=10c4f3a386d9ed51c3402c313eb57cf717cd7567 \
  --tag lucky-cat:apple-container-1.0 \
  examples/chirpui/lucky_cat

container image inspect lucky-cat:apple-container-1.0
```

The captured build log must show that multi-stage `COPY --from`, remote `ADD`,
and the `uv venv --python 3.14t` layer completed. Record the resulting image
digest and architecture.

### 3. Run with production-safe configuration

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
  --env CHIRP_ENV=production \
  --env CHIRP_DEBUG=0 \
  --env CHIRP_LOG_FORMAT=json \
  --env CHIRP_SECRET_KEY \
  --env LUCKY_CAT_FEED=sim \
  lucky-cat:apple-container-1.0

container inspect lucky-cat-apple-container
container stats --no-stream lucky-cat-apple-container
```

Do not record the generated secret. The simulated feed keeps the application
probe deterministic and avoids making upstream market services part of the OCI
compatibility result.

### 4. Exercise probes, HTML, and SSE

```bash
curl --fail --show-error http://127.0.0.1:8000/health
curl --fail --show-error http://127.0.0.1:8000/ready
curl --fail --show-error --dump-header /tmp/lucky-cat-home.headers \
  --output /tmp/lucky-cat-home.html \
  http://127.0.0.1:8000/

rg -i '^content-type: text/html' /tmp/lucky-cat-home.headers
rg '<html|id="markets-lobby"' /tmp/lucky-cat-home.html

curl --fail --show-error --no-buffer --max-time 10 \
  --header 'Accept: text/event-stream' \
  --dump-header /tmp/lucky-cat-sse.headers \
  --output /tmp/lucky-cat-sse.body \
  http://127.0.0.1:8000/ft/stream

rg -i '^content-type: text/event-stream' /tmp/lucky-cat-sse.headers
rg '^(event|data):' /tmp/lucky-cat-sse.body
```

The SSE curl is expected to end on its ten-second client timeout while the
server remains healthy; that timeout alone is not a failure. Record multiple
complete SSE events and a subsequent successful `/ready` response to prove the
connection was long-lived without wedging the app.

### 5. Prove Linux ARM64 and free-threading

```bash
container exec lucky-cat-apple-container python -c \
  'import platform, sys; print(platform.machine(), platform.python_version(), sys._is_gil_enabled()); assert platform.machine() in {"aarch64", "arm64"}; assert not sys._is_gil_enabled()'
```

The assertion must pass. Merely observing `PYTHON_GIL=0` in the environment is
not proof that a dependency did not re-enable the GIL.

### 6. Prove signal forwarding and graceful shutdown

In one terminal, follow the application output:

```bash
container logs --follow lucky-cat-apple-container
```

In another terminal, send the runtime's default graceful signal with a longer
deadline than Apple Container 1.0's five-second default:

```bash
container stop --signal SIGTERM --time 15 lucky-cat-apple-container
container inspect lucky-cat-apple-container
container logs lucky-cat-apple-container
container delete lucky-cat-apple-container
container system stop
```

The receipt must show that SIGTERM reached the Python process, Chirp completed
ASGI lifespan shutdown before the deadline, and the runtime did not escalate to
SIGKILL. A zero exit alone is insufficient if the logs cannot distinguish
graceful shutdown from termination.

## Hosted CI viability

GitHub's runner-images repository lists `macos-26`/`macos-26-xlarge` as ARM64
images. GitHub's hosted-runner documentation also says nested virtualization is
not supported on ARM64 macOS runners. Apple Container runs Linux containers in
lightweight virtual machines through Apple's Virtualization framework.

The resulting **inference** is that GitHub-hosted ARM64 macOS runners should not
be treated as a reliable Apple Container execution surface. This project should
not add a required hosted check based on those labels. Keep this as a manual or
self-hosted release smoke check on a prepared Apple Silicon host.

No hosted workflow was executed for this receipt, so actual behavior remains
manual-confirmation-needed. Revisit the decision only if GitHub explicitly
documents nested-virtualization support or an Apple Container job completes the
full matrix reliably.

## Primary sources

- [Apple Container 1.0 release](https://github.com/apple/container/releases/tag/1.0.0)
- [Apple Container 1.0 README and host requirements](https://github.com/apple/container/blob/1.0.0/README.md)
- [Apple Container 1.0 command reference](https://github.com/apple/container/blob/1.0.0/docs/command-reference.md)
- [Apple Container 1.0 resource and port-publishing guidance](https://github.com/apple/container/blob/1.0.0/docs/how-to.md)
- [GitHub-hosted runner reference](https://docs.github.com/en/actions/reference/runners/github-hosted-runners#limitations-for-arm64-macos-runners)
- [GitHub runner image labels](https://github.com/actions/runner-images#available-images)

No changelog: this is a blocked validation receipt plus an unexecuted runbook;
it changes no supported behavior or compatibility claim.
