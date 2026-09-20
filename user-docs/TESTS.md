# Testing

The active gateway and control plane test suite is entirely Rust-based.

## Prerequisites

- Rust 1.88 with `rustfmt` and `clippy`
- Node.js 20 for the dashboard build
- Docker for image and Compose validation

## Local checks

### One-command automated E2E run

```bash
make local-e2e
```

`make test-e2e` remains an alias for `make local-e2e`.
No separately running Doorman server is needed. This sequential, fail-fast runner:

1. Tests the Python verification scripts and checks the pinned reference/600-entry ledger.
2. Runs Rust formatting, Clippy, and the full Cargo suite (including protocol,
   platform, persistence, and process-lifecycle tests).
3. Installs frontend dependencies and builds the dashboard.
4. Starts isolated MongoDB/Redis with Compose and explicitly enables the external
   storage tests. An ordinary `make test` does **not** exercise those dependencies.
5. Builds the candidate Docker image, starts it with fresh test credentials and
   disposable in-memory data, checks backend readiness and frontend HTTP, and
   runs the normally ignored live TCP/auth test against that image.
6. Removes its temporary container and Compose resources, keeping logs and reports.

Requires Python 3, Git, Make, Bash, Cargo/rustfmt/Clippy, npm, and a working Docker
daemon with Compose v2. The runner finds Rust in `~/.cargo/bin` automatically.
Dependency downloads/image pulls require network access. Do **not** use `sudo make`.
The external-storage fixture uses loopback ports 27018 and 16379; these must be free
(override with `DOORMAN_TEST_MONGO_PORT` / `DOORMAN_TEST_REDIS_PORT` if needed).
The disposable candidate uses automatically assigned loopback ports and never
mounts your data or reads your root `.env`. Existing Doorman services are untouched.
Run only one E2E invocation per checkout at a time: Cargo/frontend build directories
and the default storage ports are shared. The runner stays sequential under `make -j`.

Each run creates a private, unique `release-evidence/<UTC>-<suffix>/` directory
containing per-stage logs, source revision/status, immutable local image ID, and
`summary.json`. Failed and interrupted runs keep their evidence; they cannot report
success. Evidence is gitignored and excluded from Docker builds. Set
`E2E_EVIDENCE_ROOT` to change its parent directory. Built images and dependency/build
caches are retained; the runner never prunes Docker or deletes existing project data.

Preview all gates or check tool availability without building:

```bash
make e2e-plan
python3 scripts/run_e2e.py --preflight
```

### Full release gate

```bash
make release-e2e
```

This runs everything above **plus** the operational rehearsal command, live
Python/Rust differential comparison, four-protocol performance comparison, and
`release-check`. Missing release prerequisites fail **before** expensive builds.
There are no skip flags. A passing `local-e2e` is not a release sign-off.

Additional setup is required; the repository does not yet supply an automatic
Python/seeded-upstream fixture launcher or deployment/backup rehearsal implementation:

- Export the production-like configuration variables listed under "Release evidence
  check" below. Use an isolated rehearsal environment, never a production target.
- Start the pinned Python reference and equivalent seeded Rust fixture with REST,
  GraphQL, SOAP, and gRPC upstreams. Export `PYTHON_PARITY_URL`, `RUST_PARITY_URL`,
  `PYTHON_PARITY_PID`, `RUST_PARITY_PID`, and `PARITY_PERF_SCENARIOS`. The PIDs must be
  distinct, running processes with readable RSS in this machine's `/proc` (Linux).
  The JSON scenario file must contain exactly the four protocol profiles described
  below. The operator is responsible for matching PIDs/URLs to the actual servers,
  using the pinned Python commit and the candidate image for the Rust fixture.
- Set `RELEASE_OPERATIONS_COMMAND` to an executable script implementing the isolated
  [release runbook](OPERATIONS.md#release-candidate-runbook). This is an explicit
  operator-supplied command, invoked without shell evaluation or arguments. It must
  perform and assert image smoke, restore, cutover, and rollback; clean up its own
  resources even on failure; and leave the comparison fixtures running afterward.
  It receives `RELEASE_IMAGE_ID` (the candidate's immutable local Docker ID),
  `E2E_EVIDENCE_DIR`, and `RELEASE_OPERATIONS_REPORT` in its environment. It must
  deploy/test that image and write the schema-version-1 operations report at the
  supplied path, with a top-level `image_id` equal to `RELEASE_IMAGE_ID` as well as
  the four successful rehearsal records. Include substantive request/backup evidence
  from the runbook; do not use a script that only writes `passed: true`.

The runner generates fresh report paths itself; caller-supplied old report paths
are not reused. Benchmark trials must have zero failed requests on both servers,
in addition to the existing relative no-regression thresholds. Preflight can be
run independently with `python3 scripts/run_e2e.py --release --preflight`.

The local image smoke uses HTTP/in-memory storage. The operational hook must supply
the production-like TLS/shared-storage and backup/recovery evidence. Frontend HTTP
and build checks are not browser workflow tests; this runner also does not add new
soak tests or expand the checked-in differential scenarios to all 178 operations.
Keep the remaining release review/coverage work explicit.

From the repository root:

```bash
make check
make web-build
```

The equivalent direct commands are:

```bash
cargo fmt --manifest-path gateway-rs/Cargo.toml --all -- --check
cargo clippy --manifest-path gateway-rs/Cargo.toml --locked --all-targets --all-features -- -D warnings
cargo test --manifest-path gateway-rs/Cargo.toml --locked
npm --prefix web-client ci
npm --prefix web-client run build
```

Rust integration tests use in-process upstream servers and do not require MongoDB or Redis. Storage and platform tests use the native in-memory backend. Checked-in parity fixtures preserve the pre-Rust public wire contract.

## Live smoke test

Start Doorman:

```bash
cp .env.demo .env
docker compose -f docker-compose.yml -f docker-compose.demo.yml up --build
```

In another terminal:

```bash
make smoke
```

## Shared-storage verification

Use the external profile when testing MongoDB/Redis behavior:

```bash
MEM_OR_EXTERNAL=REDIS docker compose --profile external up --build
make smoke
```

## Release evidence check

A release candidate must include a fresh zero-difference differential report, a
passing Python-versus-Rust performance report, and the log from the isolated
MongoDB/Redis suite. The final check is intentionally fail-closed:

```bash
EXTERNAL_STORAGE_LOG=release-evidence/external-storage.log \
  bash scripts/run_external_storage_tests.sh

ENV=production MEM_OR_EXTERNAL=REDIS \
HTTPS_ONLY=true CORS_STRICT=true LOCAL_HOST_IP_BYPASS=false \
DOORMAN_ADMIN_EMAIL=admin@example.com \
DOORMAN_ADMIN_PASSWORD='use-a-real-secret' \
JWT_SECRET_KEY='use-a-unique-signing-key' \
JWT_ISSUER=doorman-production JWT_AUDIENCE=doorman-clients \
ALLOWED_ORIGINS=https://admin.example.com \
DISCOVERY_ALLOWED_HOSTS=api.example.com \
MONGO_DB_HOSTS=mongo.example.com:27017 \
MONGO_DB_USER=doorman-release MONGO_DB_PASSWORD='use-a-real-mongo-secret' \
REDIS_HOST=redis.example.com REDIS_PASSWORD='use-a-real-redis-secret' \
PARITY_REPORT=release-evidence/differential.json \
PARITY_PERF_REPORT=release-evidence/performance.json \
EXTERNAL_STORAGE_LOG=release-evidence/external-storage.log \
RELEASE_OPERATIONS_REPORT=release-evidence/operations.json \
make release-check
```

Evidence defaults to a maximum age of 24 hours; set
`DOORMAN_RELEASE_EVIDENCE_MAX_AGE_HOURS` only when the release policy explicitly
allows a longer review window. Scheduled CI runs the external-storage suite and
retains its Compose logs for 14 days, including on failures.

The differential report is accepted only when it records the SHA-256 of the
checked-in `parity/differential/scenarios.json` and one result for each of its
scenarios plus the OpenAPI comparison. This prevents a partial or empty
zero-difference report from being used as release evidence.

`operations.json` is the signed-off record produced from the release runbook.
It must be a schema-version-1 JSON object with each of these fields set to
`{"passed": true}`: `image_smoke`, `restore_rehearsal`, `cutover`, and
`rollback`. The checker rejects an incomplete or failed rehearsal record.

The performance report must come from `make parity-performance` using four
representative, policy-enabled candidate routes. Set `PARITY_PERF_SCENARIOS` to
a private JSON file containing named `rest`, `graphql`, `soap`, and `grpc`
entries. Each entry has `python_url`, `rust_url`, and an optional `request`
object (`method`, string-map `headers`, and string `body`), so POST-based
GraphQL, SOAP, and gRPC requests are measured faithfully. The benchmark never
writes request headers or bodies to its report. The release checker rejects a
health-only or incomplete performance report.

## Container checks

```bash
docker compose config
docker build -t doorman:local .
```
