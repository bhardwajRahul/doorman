# Production-Ready Parity Implementation Playbook

## Purpose

This is the implementation plan for the complete v2 Rust backend replacement against the pinned Python baseline at 10699820f50abe3940134536a98c955deab6959f. The user reconfirmed on 2026-09-13 that the transition must preserve Python behavior 1:1. Public contracts, management workflows, policy effects, and persisted data must retain their behavior, except for the previously approved security differences. A passing build or a weighted readiness score alone does not establish that parity.

The target is a Rust-only deployment that has safe, verified behavior for production user journeys, external persistence, security controls, operations, and rollback. Later Python features outside the pinned reference are excluded unless product ownership explicitly adds them.

Launch assumption confirmed by the user: treat v2 as a fresh deployment with no
existing v1 users. Users must log in to v2; preserving Python sessions or carrying
forward a live v1 deployment is not a launch requirement. The pinned Python
behavior remains the functional reference, and v2 persistence, backup/restore,
and recovery verification remain required.

## Operating model for lower-tier agents

One agent owns one ticket. Do not combine tickets, refactor adjacent domains, rename public fields, alter an approved divergence, weaken a test, or change CI simply to make a gate pass.

Before editing:
- Read this playbook, PYTHON_TO_RUST_MIGRATION_AUDIT.md, parity/README.md, and the pinned Python source for the named test or behavior.
- Run git status --short. Preserve unrelated changes in the shared worktree.
- Identify the precise Rust handler or policy function, the pinned Python oracle, and the smallest existing Rust test target.

While editing:
- Prefer a focused Rust test that makes a real request through the relevant handler or a real upstream fixture where the behavior crosses a protocol boundary.
- Preserve response status, headers, envelope, and error code unless the ticket explicitly records an approved change.
- Add an exact mapping in parity/test_coverage_overrides.json only after the assertion-level Rust test passes.
- Regenerate parity/test_coverage_ledger.json with python3 scripts/generate_test_coverage_ledger.py --write.
- Do not use destructive Git commands, modify generated reference fixtures, or commit.

Before handoff:
- Run cargo fmt --manifest-path gateway-rs/Cargo.toml --all.
- Run the narrow test target and the appropriate check listed in the ticket.
- Run git diff --check.
- Report changed files, exact commands/results, remaining risk, and whether the production-ready percentage should change.

Escalate rather than guess when a task needs a product decision, a new secret, external infrastructure credentials, a baseline change, a security-policy relaxation, an incompatible wire response, or a schema choice that cannot be proven from pinned Python behavior.

## Progress score

The following is the historical weighted readiness estimate, not a verified 1:1 migration percentage. It remains unchanged until the required evidence is accepted. Full completion also requires an executable behavior matrix for the 178 pinned operations and explicit disposition of the remaining test gaps.

| Gate | Weight | Current estimate |
|---|---:|---:|
| Baseline and approved divergences | 5 | 4 |
| Build and CI integrity | 10 | 10 |
| Critical data-plane journeys | 25 | 18 |
| Security and identity | 20 | 17 |
| MongoDB and Redis behavior | 20 | 13 |
| Essential control-plane workflows | 10 | 8 |
| Operations, performance, and cutover | 10 | 4 |
| Total | 100 | 74 |

Only the lead updates this score after a complete gate. The test-ledger remains a separate evidence measure: 340 covered, 11 approved_changed, 40 approved_obsolete, and 209 missing out of 600 pinned Python tests.

## Lead execution checklist

This is the working implementation checklist. Update it in the same change as
each task: `[ ]` pending, `[~]` in progress, `[x]` implementation complete but
verification deferred, and `[G]` release-gate evidence accepted. A checked
implementation item does not change the weighted production score on its own.

### Current implementation queue

- [x] T-01 / MIG-002, E4, F2: restore Python-compatible configured snapshot
  paths for autosave, dump, and restore. The Rust filename-only guard rejected
  the persisted default `generated/memory_dump.bin`; absolute and nested
  administrator-configured paths now retain the Python behavior. Focused test
  added; the snapshot compatibility and path tests passed on 2026-09-13.
  The subsequent parity pass separates exact-file HTTP restore from startup's
  latest-dump search, fixes directory hints and default/stem fallbacks, and
  verifies missing/wrong-key/tampered restores preserve current state. Sixteen
  focused snapshot tests and an environment-isolated HTTP harness cover these
  behaviors; 14 pinned Python cases now have exact assertion mappings.
- [x] T-02 / audit maintenance: reconciled stale MIG-038, MIG-040, MIG-044,
  MIG-047, MIG-051, and the hot-reload ownership map with current source,
  without converting implementation claims into gate evidence.
- [~] T-03 / C1-C5: complete remaining security, identity, audit/redaction,
  IP/CORS, and settings runtime-effect gaps identified by the reconciled audit.
  Current pass adds authenticated actor/route context to activity records while
  retaining payload-free mutation audit events.
  The 2026-09-13 pass repairs compilation, enforces the environment localhost
  lock, applies saved proxy trust to login limiting, restores dashboard security
  metadata, verifies autosave-setting publication and rejected updates, redacts
  nested log-export credentials, and validates atomic HTTP runtime reloads.
  Focused security and platform suites pass; the complete C1-C5 matrix is still open.
  The 2026-09-15 pass adds Python-compatible security-settings JSON persistence,
  file-only memory startup recovery, database/snapshot precedence, and immediate
  first autosave when enabled. Five focused unit tests and a process-isolated
  HTTP/worker test pass; three Python file-persistence cases now have exact
  assertion mappings. The real MongoDB/Redis suite also passes, including
  external-mode rejection of file overrides. Compose places the mirror on
  its existing persistent volume. Model coercion and the remaining lifecycle
  matrix are still open; the weighted score is unchanged.
  The next settings-validation slice implements Pydantic v1 boolean coercion
  and autosave-interval coercion (ASCII integer strings, valid digit separators,
  whitespace/signs, and truncation of fractional JSON numbers). Boolean/integer
  errors now carry the Python error types and minimum context in model field
  order. Focused unit tests compare these cases against the retained pinned
  Python image, running Pydantic 1.10.26; this is not a dependency-lock claim.
  The HTTP regression checks typed persistence, runtime publication, null/unknown
  handling, and atomic rejection. No additional pinned Python test is marked
  covered solely for these new model-derived regressions; the ledger stays at
  340 covered and 209 missing.
  The typed-record follow-up corrects management reads/updates, platform IP
  filtering, login IP limiting, and gateway policy to select the security type.
  Updates no longer replace the settings collection for identifier-free memory
  records. New memory and policy regressions reproduced the original defects;
  the separate eight-test MongoDB/Redis run verifies HTTP updates, reconnection,
  BSON identifier preservation, and unrelated-record preservation. Authentication
  and platform IP fixtures now also include unrelated settings documents.
  The autosave-lifecycle follow-up preserves positive environment/file intervals
  below 60 seconds while retaining the worker's 60-second minimum wait, and
  accepts surrounding whitespace in environment enablement and interval values.
  New process-isolated tests exercise real encrypted snapshots with a controlled
  Tokio clock: immediate startup, minimum/cadence timing, path and cadence updates,
  disablement, failed-write health, scheduled recovery, and worker cancellation.
  These are source-derived regressions; no new pinned test mapping or readiness
  score increase is claimed. Full process/signal and cross-process coverage
  remains open.
  The dump-path model follow-up accepts JSON boolean/integer/float inputs with
  Python spelling and emits `type_error.str` for invalid container values.
  The retained Pydantic model matches 9,995 sampled finite float conversions,
  including shortest-decimal ties that differ from Rust's default formatter.
  Unit and authenticated HTTP regressions verify normalized persisted/file/read
  and runtime paths, field-order errors, and atomic rejection. Unicode integer,
  unbounded integer, list-item, and process/signal gaps remain in MIG-044.
  The Unicode integer follow-up now accepts all 680 decimal digits supported
  by the retained Python image, including mixed scripts and valid separators.
  Model and environment parsing share the decimal grammar while preserving
  Python's differing whitespace rules. Unit, HTTP/file/runtime atomicity,
  and isolated environment regressions pass. No new pinned test mapping or
  readiness score increase is claimed; remaining model boundaries are in MIG-044.
  The list-model follow-up restores Python scalar-to-string coercion, indexed
  null/container errors, non-list errors, and arbitrary string acceptance for
  all three security lists. The shared matcher supports dotted IPv4 masks and
  Python whitespace while rejecting signed CIDR prefixes. Two policy regressions
  reproduced the old failures; HTTP coverage verifies persistence, atomic
  rejection, and trusted/untrusted-peer policy effects. Remaining gates stay open.
  The integer-limit follow-up adds the fixed Pydantic 4,300-character guard and
  CPython's separate configurable decimal-digit limit. Startup validates and
  captures `PYTHONINTMAXSTRDIGITS`; the environment autosave parser retains its
  distinct digit-only guard. Pure unit and process-isolated configuration/HTTP
  regressions pass, including configured/unlimited limits and atomic rejection.
  Python's unbounded integer representation and the wider lifecycle remain open.
  The control-plane follow-up restores FastAPI's validation-before-handler order
  for malformed JSON on shared entity and subscription mutations, preserving
  `422 VAL001 Validation Error` before authentication. Subscription management
  now also applies Python's target-user group gate before either subscription
  mutation. Focused native regressions pass; broader Pydantic model coverage and
  the remaining authorization matrix stay open.
  The gateway-header follow-up strips Python's control characters and complete
  HTML-like tags from forwarded allowed-header values, applies the same
  8,192-character truncation marker, and never forwards sensitive headers even
  when they appear in a configured allow-list. Unit and real-local-upstream
  regressions pass; the broader gateway protocol matrix remains open.
- [ ] T-04 / B1-B5: complete and document the outstanding REST, GraphQL, SOAP,
  gRPC, gRPC-Web, and routing behavior gaps.
- [ ] T-05 / D2-D5: complete external-store persistence, outage, concurrency,
  atomicity, and memory-versus-external equivalence behavior.
- [~] T-06 / E1-E5: complete remaining control-plane validation, lifecycle,
  authorization, persistence, configuration, and vault behavior.
  In progress: correct configuration imports to merge by Python natural keys,
  preserve unrelated records and BSON identifiers, and snapshot the same state
  atomically in memory and MongoDB. Existing malformed-import coverage was
  corrected to assert preserved pre-existing records instead of emptied collections.
- [~] T-07 / F1-F5: complete operational readiness, lifecycle, performance,
  cutover, differential, rollback, and restore implementation and procedures.
- [~] T-08 / release verification: run the complete non-Docker verification
  sequence, repair defects, collect evidence, then run the external-service
  and image gates only when the environment is available.

### Local continuation evidence (2026-09-13 through 2026-09-14)

The pinned Python image and Rust candidate were run on isolated loopback ports
with synthetic data, not a production deployment. The candidate image manifest
is `sha256:a2148e454d0da04e577738f8ea08d009ae633939a757166f3fdec2e0257b6052`
(`doorman:rust-migration-20260913`). Newer frontend/authentication edits in the
shared worktree postdate this image and require their own image verification.
The newer worktree was separately rechecked: all 245 exercised Rust tests,
Clippy, formatting, pinned reference/ledger verification, and the frontend build
pass. The frontend build retains lint warnings; no warnings were suppressed.

- The candidate suite exercised 245 Rust unit/integration tests successfully;
  seven real MongoDB/Redis tests passed separately, as did the normally ignored
  live TCP probe. Do not count the external tests' environment-free early returns
  as storage evidence.
- Candidate image build, frontend build, Clippy, and smoke checks passed.
  The public differential has zero unapproved differences across nine scenarios
  plus OpenAPI; it retains three report entries for the two previously approved
  differences, MIG-068 and MIG-074. This is not a 178-operation comparison.
- A pinned Python process wrote a DMP1 snapshot. Rust restored the user password
  and five configuration collections, retaining API/endpoint identifiers. Rust
  then wrote a new group, dumped on graceful shutdown, and recovered that group
  after both restart and replacement of the container using a named volume.
- Fresh Python processes separately restored the untouched pre-cutover snapshot
  and the Rust-written snapshot. Both authenticated successfully; the latter
  also recovered the Rust-written group. This verifies the tested record shapes,
  not all bytes, descriptors, secrets, policy counters, or storage modes.
- Evidence retained locally: `/tmp/doorman-migration-differential.json`,
  `/tmp/doorman-migration-external-storage-final.log`,
  `/tmp/doorman-rust-cutover-20260914.log`, and encrypted synthetic snapshots
  `/tmp/doorman-python-cutover-20260913.bin` and
  `/tmp/doorman-rust-restart-20260914.bin`. These temporary artifacts must be
  regenerated and retained by the release workflow before release acceptance.
- Cleanup removed only the seven temporary rehearsal containers. The images,
  encrypted fixtures, logs, and named volume `doorman-rust-cutover-data-20260913`
  remain available locally; no production service or data was changed.

**Resolved cutover decision:** The user requires a fresh login and directs us to
assume no one used v1. Python sessions are intentionally not carried forward;
there will be no legacy-token compatibility mode. Rust's issuer/audience
validation remains unchanged. This closes the session-policy decision, not the
remaining release gates. Performance, the operation/test matrix, and v2
persistence/recovery verification remain open; the readiness score is unchanged.
Legacy Python file migration is compatibility work, not a prerequisite to this
fresh deployment.

## Required release gates

### Snapshot/restore follow-up verification

- The updated source passes all 258 exercised Rust unit/integration tests,
  including the isolated-process memory-route harness, plus Clippy, formatting,
  reference/ledger verification, and `git diff --check`.
- Seven external-storage tests take their environment-free early-return path
  in this run; their earlier separate service-backed result is historical,
  not a new external-storage run. The separate live-TCP test remains ignored
  in the default suite.
- The freshly built executable was separately booted on loopback with an
  encrypted synthetic snapshot. Login, five restored configuration collections,
  the retained post-cutover marker, liveness, and readiness passed. Temporary
  startup fixtures are retained under `/tmp/doorman-snapshot-startup.AoqLLe`.
- No new image/performance/full-operation differential gate is claimed for
  this slice. Remaining memory contracts, security-settings lifecycle/model
  cases, and the wider operation matrix remain queued.

### Security-settings persistence follow-up verification (2026-09-15)

- All 264 exercised Rust unit/integration tests pass. The default suite's seven
  external-storage early returns are excluded from that count; all seven also
  passed separately against isolated MongoDB/Redis services, including the new
  file-versus-MongoDB precedence assertions. The separate live-TCP test remains
  ignored in the default suite.
- Clippy (`--all-targets --all-features -D warnings`), formatting, pinned-reference
  checks, regenerated ledger validation, and `git diff --check` pass.
- Both Compose configurations validate. The primary configuration required a
  synthetic `MONGO_DB_PASSWORD` for interpolation only; no user `.env` was changed
  and this validation did not start services.
- The freshly built binary booted on loopback from an isolated JSON settings
  file without a snapshot. Fresh login, six persisted settings, liveness, and
  readiness passed. Fixtures remain at `/tmp/doorman-settings-startup.CzyMO7`.
  External-run logs are `/tmp/doorman-security-settings-external-20260915.log`;
  temporary service containers and their network were cleaned up.
- This slice does not establish a new image, performance, or complete-operation
  differential gate. The weighted readiness score remains unchanged.

### Security-settings scalar-validation verification (2026-09-15)

- All 267 exercised Rust unit/integration tests pass, including two new
  model-coercion unit tests and the new authenticated HTTP regression. The
  security-settings target separately passes all nine tests.
- Clippy (`--all-targets --all-features -D warnings`), formatting, pinned
  reference/ledger validation, and `git diff --check` pass.
- The Python oracle was the retained `doorman:python-reference-10699820`
  image, run with networking disabled and removed after each model probe.
  Its Pydantic version is 1.10.26. Boolean and integer acceptance, normalized
  values, rejection types/context, and digit-separator boundaries were checked.
- No new MongoDB/Redis service run or image-release gate is claimed for this
  slice. The default suite's seven external-storage early returns are excluded
  from the 267 count; the separate live-TCP test remains ignored.
- That scalar-validation slice added no pinned mapping. The current ledger is
  340 mapped Python cases, with 209 missing and fifty-one approved dispositions.
  Full model parity is still open, as detailed in MIG-044.
  The subsequent typed-record follow-up implements the queued lookup and
  mixed-record persistence/policy corrections. Remaining model and autosave
  lifecycle cases are next; the complete security gate remains open.

### Typed security-record verification (2026-09-15)

- All 269 exercised Rust unit/integration tests pass, including the new policy
  and mixed-record HTTP regressions. All ten security-settings tests pass.
  The identifier-free, security-record-first update case was also rerun
  separately after strengthening its ordering assertion.
- All eight external-storage tests pass against isolated MongoDB/Redis, including
  authenticated settings GET/PUT, unrelated-record preservation, BSON `_id`
  preservation, and reconnect recovery. Logs:
  `/tmp/doorman-typed-settings-external-20260915.log` and
  `/tmp/doorman-typed-settings-services-20260915/compose.log`.
  The runner removed only its temporary service containers and network.
- Clippy (`--all-targets --all-features -D warnings`), formatting,
  reference/ledger verification, and `git diff --check` pass.
- The eight external tests' environment-free early returns are excluded from
  the 269 count. The separate live-TCP test remains ignored in the default
  suite. No new image/performance/full-operation release gate is claimed.
- The new cases are source-derived regressions, not additional pinned test
  mappings. The ledger now records 340 covered, 209 missing, and fifty-one approved
  dispositions. Remaining model and autosave-lifecycle gaps are recorded in
  MIG-044; the historical readiness score remains unchanged.

### Autosave environment and worker verification (2026-09-15)

- The two new `autosave_lifecycle` tests pass. Seven environment cases were
  independently compared with `_env_bool` and `_env_int` extracted from the
  pinned Python source, without importing its application dependencies.
- The worker test uses child-process environment isolation, a controlled Tokio
  clock, real encrypted files, and restoration of a newly written record. It
  exercises immediate startup, the 60-second minimum, changed cadence/path,
  disablement, write failure, health recovery on the next scheduled attempt,
  and cancellation. Timer assertions allow Tokio's millisecond rounding.
- Build artifacts use `CARGO_TARGET_DIR=/tmp/doorman-autosave-target` because
  the existing repository target directory contains unwritable cache files.
  Focused results: `/tmp/doorman-autosave-focused.log`.
- Clippy (`--all-targets --all-features -- -D warnings`), formatting,
  pinned-reference/ledger verification, and `git diff --check` pass. Clippy
  results: `/tmp/doorman-autosave-clippy.log`; parity results:
  `/tmp/doorman-autosave-parity.log`.
- The complete Rust suite passes: 271 exercised tests, with eight external-store
  early returns excluded and one live-TCP test ignored. The initial sandboxed
  run could not bind three local fixture listeners; the complete run passed
  outside that restriction. Results: `/tmp/doorman-autosave-suite.log`.
- No MongoDB/Redis, image, performance, or full-operation differential gate is
  claimed. Ledger counts and the historical readiness score remain unchanged.
  Next: remaining settings-model coercion and real-process/signal lifecycle
  coverage recorded in MIG-044.

### Dump-path model verification (2026-09-15)

- The new dump-path unit regression passes; all 11 security-settings integration
  tests pass. Coverage includes scalar spelling, empty/null handling in model
  validation, shortest-decimal ties, string-type errors, field order, HTTP
  GET/PUT, database/file persistence, runtime publication, and rejected updates
  preserving previous settings. Logs: `/tmp/doorman-dump-path-unit.log` and
  `/tmp/doorman-dump-path-settings.log`.
- The retained `doorman:python-reference-10699820` image, with networking
  disabled, runs Pydantic 1.10.26. Direct model probes and a deterministic sample
  of 9,995 finite binary64 values match the Rust conversion. Sample inputs and
  candidate spellings: `/tmp/doorman-float-oracle-cases.json`; standalone Rust
  probe: `/tmp/doorman-float-spelling.rs`. This sample does not prove every
  possible float input or large Python integer.
- Ryū is now an explicit dependency on its existing locked version. The offline
  lockfile update adds only the dependency edge; no package version changed.
  Formatting, Clippy (`--all-targets --all-features -- -D warnings`),
  pinned-reference/ledger verification, and `git diff --check` pass. Logs:
  `/tmp/doorman-dump-path-clippy.log` and `/tmp/doorman-dump-path-parity.log`.
- The complete locked Rust suite passes: 273 exercised tests, excluding eight
  external-store early returns; one live-TCP test remains ignored. The run used
  loopback fixture access outside the sandbox, as in the prior continuation.
  Results: `/tmp/doorman-dump-path-suite.log`. No new MongoDB/Redis run is claimed.
- No additional pinned test mappings or readiness score increase is claimed.
  Remaining model and real-process/signal gaps are recorded in MIG-044.
  External-store, image, performance, and complete-operation gates remain open.

### Unicode integer verification (2026-09-15)

- Two new parser unit tests and the extended scalar-model tests pass. All 12
  security-settings integration tests and both autosave-lifecycle tests pass.
  The new HTTP regression verifies numeric GET/PUT/document/file/runtime values,
  typed integer/minimum errors, and unchanged persistence/runtime settings after
  malformed or below-minimum updates. Logs:
  `/tmp/doorman-unicode-integer-unit.log`,
  `/tmp/doorman-unicode-integer-model.log`, and
  `/tmp/doorman-unicode-integer-focused.log`.
- The retained Python image runs Unicode 15.0.0. A standalone probe scans the
  full Rust Unicode scalar range; its 680 accepted decimal digits and their
  values exactly match the image's `unicodedata` table. The ten added environment
  cases match `_env_bool`/`_env_int` extracted from its pinned source. Direct
  Pydantic probes verify Unicode minimum errors, numeric lookalikes, separators,
  and the model/environment whitespace distinction. Oracle runs disabled
  networking and removed their containers. Probe/table evidence:
  `/tmp/doorman-unicode-integer-probe.rs` and
  `/tmp/doorman-unicode-decimal-table.csv`.
- Formatting, Clippy (`--all-targets --all-features -- -D warnings`),
  pinned-reference/ledger verification, and `git diff --check` pass. Logs:
  `/tmp/doorman-unicode-integer-clippy.log` and
  `/tmp/doorman-unicode-integer-parity.log`.
- The complete locked Rust suite passes: 276 exercised tests, excluding eight
  external-store early returns; one live-TCP test remains ignored. Loopback
  fixtures ran outside the sandbox as in prior continuations. Results:
  `/tmp/doorman-unicode-integer-suite.log`. External services were not rerun.
- Ledger counts and the readiness score remain unchanged. No new external-store,
  image, performance, or complete-operation gate is claimed. Large-integer and
  integer-string digit-limit behavior, list-item conversion, and the complete
  process/signal lifecycle remain in MIG-044.

### List-model and IP-pattern verification (2026-09-15)

- The new model unit test and both IP-pattern unit regressions pass. The latter
  failed against the previous matcher (dotted masks were ignored; signed numeric
  prefixes could authorize). Before/after evidence:
  `/tmp/doorman-list-ip-before.log` and `/tmp/doorman-list-ip-after.log`;
  model result: `/tmp/doorman-list-settings-unit.log`.
- All 13 security-settings integration tests and both autosave-lifecycle tests
  pass. The new HTTP case verifies scalar/string lists, GET/PUT/document/file
  persistence, immediate whitelist/blacklist/proxy effects with direct-peer
  request context, invalid-only allowlist denial, ordered indexed errors,
  rejected updates preserving stored/file/runtime state, null preservation,
  and empty-list clearing. Results: `/tmp/doorman-list-settings-focused.log`.
- The retained Python image was run with networking disabled. Pydantic model
  probes verify list coercion and error types/locations; the runtime cases match
  `_ip_in_list` extracted from the pinned source. Oracle containers were removed.
- Formatting, Clippy (`--all-targets --all-features -- -D warnings`),
  pinned-reference/ledger verification, and `git diff --check` pass. Results:
  `/tmp/doorman-list-settings-clippy.log` and
  `/tmp/doorman-list-settings-parity.log`.
- The complete locked Rust suite passes: 280 exercised tests, excluding eight
  external-store early returns; one live-TCP test remains ignored. Loopback
  fixtures used the same access as prior continuations. Results:
  `/tmp/doorman-list-settings-suite.log`. External services were not rerun.
- No new pinned mapping or readiness increase is claimed. Remaining model,
  IP/proxy-chain, and process/signal matrices remain in MIG-025/MIG-044.
  No new external-store, image, performance, or complete-operation gate is claimed.

### Integer-string limit verification (2026-09-15)

- Four scalar-parser unit tests, all 14 security-settings integration tests,
  and all three autosave/configuration tests pass. New cases distinguish raw
  character counts from decimal-digit counts using leading zeros, Unicode,
  signs, spaces, and separators. The process-isolated HTTP test exercises default,
  640, unlimited, and 5,000-digit settings; it checks typed persistence/runtime
  publication, invalid updates preserving the document/file/runtime state, and
  valid-length below-minimum inputs retaining Python's minimum-value error.
  Results: `/tmp/doorman-integer-limits-unit.log` and
  `/tmp/doorman-integer-limits-focused.log`.
- The retained Python image's bundled `pydantic/validators.py` applies a fixed
  `max_str_int = 4300` to the entire untrimmed string. Direct Pydantic probes verify
  the character boundaries; subprocess CPython probes verify the default,
  configured/unlimited limits, exact startup grammar, and 32-bit upper bound.
  Oracle runs used networking-disabled temporary containers.
- Formatting, Clippy (`--all-targets --all-features -- -D warnings`),
  pinned-reference/ledger verification, and `git diff --check` pass. Results:
  `/tmp/doorman-integer-limits-clippy.log` and
  `/tmp/doorman-integer-limits-parity.log`.
- The complete locked Rust suite passes: 284 exercised tests, excluding eight
  external-store early returns; one live-TCP test remains ignored. Loopback
  fixtures used the same access as prior continuations. Results:
  `/tmp/doorman-integer-limits-suite.log`. External services were not rerun.
- Both Compose configurations now pass through `PYTHONINTMAXSTRDIGITS` with
  the 4,300 default; configuration docs describe its scope and fixed API limit.
  Both `docker compose config --quiet` checks pass. Primary interpolation used
  a synthetic MongoDB password; no services started and no user `.env` changed.
- Ledger counts and the readiness score remain unchanged. No new external-store,
  image, performance, or complete-operation gate is claimed. Unbounded integer
  representation, general JSON/model integer parity, and full process/signal
  lifecycle coverage remain open.

### Memory process-lifecycle verification (2026-09-15)

- Restart now reads the saved settings file solely to select the dump location;
  it restores the snapshot before loading authoritative settings or starting
  autosave. This selection does not write defaults over an existing mirror.
  SIGUSR1 and final shutdown use the published settings path, including accepted
  API changes. The SIGUSR1 handler is registered before the listener opens.
- SIGTERM/SIGINT first trigger Axum request draining. Main then stops and awaits
  the autosave and SIGUSR1 task handles, writes the final snapshot, and persists
  metrics. A mutation completed during draining is included in the restart state.
- Pinned `doorman.py` uses cached settings paths for startup and signals. The
  retained image's `uvicorn.server.Server.shutdown` confirms that request draining
  precedes the Python lifespan shutdown dump. Python logs restore exceptions;
  Rust retains its existing refusal to start from unreadable selected snapshots.

| Behavior | Process evidence | Remaining boundary |
| --- | --- | --- |
| Saved path after API update, autosave disabled | SIGUSR1 snapshot, forced stop, restart, fresh login, API read | Concurrent updates/signals |
| SIGINT shutdown | Successful exit, final dump log, metrics file | Repeated signals and write failures |
| SIGTERM active request | `100 Continue` confirms body extraction before signal; body released during drain returns 201 and survives restart | Forced termination during drain |
| Enabled startup autosave | Restored API survives; restore log precedes first autosave log | Complete startup/background-task matrix |
| Wrong-key/corrupt selected snapshot | Nonzero startup exit; snapshot directory bytes unchanged | All filesystem failure modes |
| SIGHUP, external-mode signals, Windows | No new process evidence | Still open in MIG-044/MIG-047 |

- The three checked-in regressions run the actual gateway binary in isolated
  directories with synthetic configuration. The baseline run exposed shutdown
  writing the environment path and wrong-key startup failing to refuse the
  saved-path snapshot. Focused repaired tests pass:
  `/tmp/doorman-process-before.log` and `/tmp/doorman-process-after.log`.
- No additional pinned test mapping or readiness score increase is claimed.
  Cross-process publication and the remaining signal/task matrix stay open.

### Release checklist

Every gate must be green before release:
- make parity-reference
- make parity-ledger
- cargo fmt --manifest-path gateway-rs/Cargo.toml --all -- --check
- cargo clippy --manifest-path gateway-rs/Cargo.toml --locked --all-targets --all-features -- -D warnings
- cargo test --manifest-path gateway-rs/Cargo.toml --locked
- npm --prefix web-client run build
- Docker image build
- external MongoDB and Redis integration suite
- real TCP protocol suite for REST, GraphQL, SOAP, and gRPC
- controlled Python-versus-Rust differential report with only approved differences
- documented smoke, complete Python-to-Rust cutover, recovery, and restore rehearsal

## Workstream A: release integrity and CI

Owner profile: reliable implementation agent. Dependencies: none.

A1. Make CI execute the same required release commands listed above, separating fast pull-request checks from external-service/nightly checks.
A2. Add an artifact policy: differential reports, benchmark reports, and external-service logs are retained for failed runs.
A3. Add a release-check script that fails if required environment variables, generated ledgers, or reports are missing.
A4. Verify the frontend build from web-client, not repository root.

Done when: a clean checkout runs all fast gates without manual path correction; external gates have documented Compose/Testcontainers setup and are runnable in CI.

Current A evidence: the pull-request workflow runs formatting, pinned-reference and ledger checks, Clippy, the complete Rust suite, the `web-client` build, and the Rust-only image build. A scheduled/manual external-storage job invokes the isolated Compose suite and retains Compose logs for 14 days even when the suite fails. `scripts/release_check.py` is a fail-closed final evidence check: it validates production TLS/CORS/localhost policy and external-store credentials, fresh differential/performance/external logs, and the generated parity checks. Its focused regression test passes.

## Workstream B: critical data-plane journeys

Owner profile: protocol-focused implementation agent. Dependencies: A1 for CI wiring.

B1. REST real-upstream matrix: public and authenticated APIs, subscription checks, rate/bandwidth/credit enforcement, routing precedence, retries, timeout, transformed request/response, and exact gateway errors.
B2. GraphQL real-upstream matrix: authenticated and public access, variables, operation selection, depth/size failures, CORS, upstream errors, and disabled API behavior.
B3. SOAP real-upstream matrix: XML body forwarding, SOAPAction, SOAP versions, auth, subscription, CORS, upstream status/body handling, and disabled API behavior.
B4. gRPC and gRPC-Web matrix: unary request forwarding, metadata, deadlines, descriptors, error/status mapping, CORS/preflight, and an explicit supported-streaming policy.
B5. Routing matrix: client routing beats endpoint routing, endpoint beats API, round-robin persists in Redis, and no-server behavior is stable.

Current B4 evidence: real HTTP/2 upstream tests cover descriptor-backed unary forwarding, metadata/deadline propagation, upstream status mapping, and server/client/bidirectional JSON gateway streaming. `grpc_web_unary_cors_and_streaming_policy_parity` also covers binary gRPC-Web unary framing/trailers, authenticated browser preflight/CORS, and the explicit `UNIMPLEMENTED` policy for client/bidirectional streaming. `external_grpc_descriptor_and_subscription_survive_router_restart` proves that a fresh router can load the API, descriptor, endpoint, and subscription from real isolated MongoDB/Redis and forward the same gRPC request. gRPC-Web has no pinned Python test ID, so this capability test intentionally has no ledger mapping.

Current B5 evidence: `routing_precedence_and_round_robin_real_upstreams_parity` sends real authenticated requests through six local TCP upstreams and proves client routing wins over endpoint/API servers, endpoint routing wins over API servers, and client/endpoint/API round-robin order is stable. `external_concurrent_policy_state_is_atomic_and_invalidates_across_instances` separately proves Redis routing indexes remain atomic across two external-storage clients. `gateway_no_upstream_servers_has_stable_error_contract` verifies the authenticated no-server path returns the stable 404/GTW001 response without attempting an upstream call.

Current B2 evidence: descriptor-free real-upstream tests cover authenticated GraphQL basic forwarding, variables plus endpoint validation, disabled API rejection, CORS, and public access. `graphql_public_error_envelope_normalizes_upstream_status_parity` verifies a public GraphQL request passes an upstream GraphQL errors envelope through intact and normalizes an upstream 500-with-errors response to the pinned HTTP 200 contract.

Current B3 evidence: real XML upstream tests cover authenticated SOAP forwarding, SOAPAction, public bulk operations, CORS/preflight, and XML content handling. `soap_content_types_and_retry_real_upstream_parity` verifies both accepted XML content types and a real upstream 503 followed by the configured single retry and success.

Current B1 evidence: real REST upstream tests cover protected/public forwarding, routing precedence, subscriptions, rate/bandwidth/credit effects, CORS, retries, and request/response header allowlists. `rest_retries_real_upstream_status_sequences_parity` verifies actual 500/503 retry-once behavior and exact zero-retry behavior with independent per-API upstream attempt counts. `rest_request_and_response_header_allowlists_real_upstream_parity` verifies a real upstream receives only approved request headers and that only approved response headers are exposed to clients.

Done when: each B ticket uses an actual local TCP upstream or gRPC server and passes both memory and external-store modes where it uses state.

## Workstream C: security and identity

Owner profile: security-conscious implementation agent. Dependencies: B1 for protected data-plane coverage.

C1. Token lifecycle: expired JTI revocations cease to apply; expiry/TTL and cleanup work in memory and Redis; refresh reloads current user role and permissions.
C2. Authentication wire behavior: cookie attributes, configured lifetimes, CSRF modes, malformed JSON, issuer/audience/kid/key rotation, inactive users, and proxy trust behavior.
C3. Management authorization: explicit permissions for every production-used control-plane mutation; tests cover allowed, forbidden, self-service, and administrator cases.
C4. Audit and redaction: centralize sensitive-header/value redaction; emit structured records for management mutations and security decisions; verify exported logs never expose secrets.
C5. IP and CORS: trusted forwarded address rules, allow/deny lists, localhost policy, preflight behavior, credentialed origins, and rate-limit headers.

Current C2 evidence: isolated child-process login cases now prove the pinned
default Strict/non-Secure cookies, `COOKIE_SAMESITE=Lax`, the non-Secure
SameSite=None downgrade to Lax, HTTPS_ONLY Secure SameSite=None behavior, and
host-only `testserver` cookies. A structurally valid JWT signed with the wrong
HS256 secret is rejected as HTTP 401 `AUTH003`. Five pinned cookie/JWT cases now
have assertion-level ledger mappings. Full native platform coverage passes all
46 tests. Cookie lifetime, refresh/status wire bodies, issuer/audience/kid
rotation, inactive-user, and direct/proxy authentication cases remain open.

Current C4 evidence: a payload-free audit record is centrally emitted for every authenticated POST/PUT/PATCH/DELETE platform request, with only a static route family target and success/failure status; configuration export has its own read audit event. `redacted_headers` and `redacted_value` provide the only supported structured audit views for untrusted metadata, masking authorization, cookies, API keys, passwords, tokens, credentials, and secret-named values; a unit test proves those literals do not survive the redaction boundary. IP-denial events record only parsed effective/direct IPs and never raw forwarded-header input. The full Rust suite passes, including global IP-denial, config-export, and payload-free mutation regression coverage.

Done when: no production API key, token, password, authorization header, or vault value can be returned or logged; security behavior is validated in both direct and proxy request modes.

## Workstream D: external MongoDB and Redis

Owner profile: storage/integration implementation agent. Dependencies: A1.

D1. Add deterministic external-service test fixtures using the repository's supported Compose or Testcontainers approach. Tests must use isolated database names and key prefixes.
D2. Verify persisted CRUD and restart recovery for APIs, endpoints, users, roles, groups, subscriptions, credits, tiers, routings, settings, and config snapshots.
D3. Verify TTL and concurrency for revocations, login rate limits, throttles, bandwidth, routing indexes, and cache invalidation across two Rust instances.
D4. Verify failure behavior: unavailable Redis, unavailable MongoDB, reconnect, read-only or timeout conditions, and no partial config import.
D5. Verify indexes, uniqueness, BSON identifier conversion, atomic increments, and memory-versus-external response equivalence.

Current D4 evidence: external startup fails closed when either dependency is unavailable. Multi-collection configuration import and rollback now use one memory-store lock or a single MongoDB transaction, including snapshot creation; external deployments without MongoDB transaction support fail the operation before any collection is replaced rather than producing partial configuration state. The Compose fixture uses an isolated single-node MongoDB replica set (the minimum transaction-capable topology), and all seven external MongoDB/Redis tests pass, including the persisted API/endpoint import-and-rollback path.

Done when: stateful production policies have external-mode tests, no test shares data across runs, and outage behavior produces documented status/error responses.

## Workstream E: essential control plane

Owner profile: CRUD/model implementation agent. Dependencies: D2 for persistence-sensitive cases.

E1. APIs and endpoints: positive, authorization, validation, not-found, unsupported-method, and persistence cases.
E2. Users, roles, and groups: lifecycle, assignment restrictions, password changes, permission hierarchy, and protected resource rules.
E3. Subscriptions, credits, tiers, routings, and rate limits: customer-facing lifecycle and policy effects proven through data-plane requests.
E4. Configuration and security settings: validate before mutation, atomic import/rollback behavior, effective runtime settings, and truthful response values.
E5. Vault: encryption at rest, no plaintext response/logging, value replacement, ownership rules, and restart behavior.

Current E5 evidence: the vault collection now has a unique external-store index on `(username, key_name)`. `vault_lifecycle_encrypts_at_rest_and_never_returns_the_secret` creates, reads, updates, and deletes an authenticated user-owned entry, proves the stored value is versioned ciphertext rather than plaintext, and proves list/get/create responses do not contain the secret. The external collection restart suite also persists a vault entry through a fresh shared-storage connection.

Done when: every production-used operation has a focused positive, forbidden, validation, not-found, and external-persistence test. Do not pursue exact cosmetic validation-message parity unless it affects clients or security.

## Workstream F: operations and cutover

Owner profile: release/operations implementation agent. Dependencies: B through E.

F1. Readiness and monitor endpoints must reflect actual dependencies, descriptor availability, and storage health rather than placeholders.

Current F1 evidence: readiness now independently probes MongoDB and Redis and inspects active non-CRUD gRPC APIs for a non-empty descriptor set. Missing descriptors (or failed descriptor inspection) return HTTP 503 and degrade readiness; privileged readiness returns the exact count and affected API/version without exposing descriptor contents. `readiness_degrades_when_an_active_grpc_api_lacks_a_descriptor` passes as focused regression coverage for this fail-closed path. The release smoke preflight now rejects a degraded readiness result.
F2. Process lifecycle: startup validation, graceful shutdown, snapshot behavior, restore, background-task failure, and signal behavior.

Current F2 evidence: memory snapshots are encrypted, atomically written, restored at startup, and dumped on SIGTERM/CTRL-C and SIGUSR1. Startup treats a missing snapshot as first boot but fails closed for a corrupt, unauthenticated, or unsupported-version snapshot rather than serving empty state. Memory-snapshot and metrics-persistence background failures now feed privileged readiness and return HTTP 503 until the task succeeds again. `rejects_unsupported_snapshot_version` and `readiness_degrades_when_a_background_persistence_task_is_unhealthy` pass as regression coverage.
F3. Performance: record REST, GraphQL, SOAP, and gRPC latency/throughput baselines at representative policy loads; define pass thresholds and regression tolerance.

Current F3 evidence: `make parity-performance` now requires paired Python/Rust URLs for named REST, GraphQL, SOAP, and gRPC profiles. It records alternating-trial throughput, p95, error rate, and peak RSS with a configurable regression tolerance. The release-evidence checker rejects a performance report unless all four profiles have numeric Python/Rust metrics and no failures; real candidate measurements remain required before this gate can close.
F4. Deploy: run an image smoke test, migration/restore rehearsal, full Python-to-Rust cutover procedure, recovery procedure, and incident runbook. V2 is a complete backend switch; a pre-existing v2 staging deployment or canary image is not a prerequisite.
F5. Differential: run pinned Python and Rust separately against shared scenario fixtures; classify every difference as fixed or approved.

Current F5 evidence: the differential runner records the SHA-256 of the checked-in scenario manifest. The release-evidence checker requires that exact digest and one result for every manifest scenario plus OpenAPI, rejecting empty or partial zero-difference artifacts. A controlled run against the pinned Python reference and the freshly built `doorman:rust-rewrite-candidate` image completed with zero unapproved differences. The report retains the approved strict cache-preflight change (MIG-068) and the reviewed private documentation/OpenAPI surface (MIG-074); it was produced under equivalent CORS and public-registration test configuration. The fresh release run must retain its generated report as the `PARITY_REPORT` evidence input.

Current F4 evidence: `user-docs/OPERATIONS.md` now contains candidate-image smoke, restore, complete Python-to-Rust cutover, and backup-based Python recovery procedures. `scripts/release_check.py` requires a fresh schema-versioned operations report with `image_smoke`, `restore_rehearsal`, `cutover`, and `rollback` evidence alongside differential, performance, external-storage, and generated-parity evidence; its regression test rejects incomplete operational evidence. Written procedures do not count as completed rehearsals.

Done when: a release candidate can be deployed, checked, canaried, rolled back, and restored by documented commands without Python fallback.

## Ticket template

Use this exact structure in each lower-tier assignment:

Title: short domain and behavior
Scope: exact files/routes/pinned Python tests
Do not change: unrelated domains, public contracts outside scope, baseline, CI policy
Implement: numbered observable behaviors
Tests: exact Rust test target(s), plus real upstream/external service requirement if applicable
Ledger: exact Python IDs to map, or say no ledger mapping expected
Verification: narrow command, formatting command, relevant release command
Done when: observable acceptance criteria
Escalate if: product choice, compatibility ambiguity, credentials/infrastructure, or security divergence

## Lead integration order

1. A1-A4 and D1 establish trustworthy execution.
2. C1-C5 and B1 establish security-safe REST production behavior.
3. D2-D5 plus B2-B5 establish durable multi-protocol behavior.
4. E1-E5 closes production-used control-plane paths.
5. F1-F5 produces the release evidence and raises the production-ready score to 100.

No agent may declare production-ready status. Only the lead may mark a gate complete after reviewing the diff, test evidence, external-service evidence, and any parity disposition changes.
