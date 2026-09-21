# Doorman Local System-Test Program — Implementation Status

Last updated: 2026-09-20

## Overall status

**Partially implemented; not release-complete.**

The offline contract, deterministic coverage generation, fixture foundation,
memory-topology bootstrap, evidence model, developer commands, cleanup ownership,
and release-evidence validation are implemented. The runtime corpus is deliberately
fail-closed while the remaining scenario executors and topologies are incomplete.

Do not treat a passing `make system-e2e-check` as a passing product run. It validates
the harness manifests and generated coverage ledger only. At this checkpoint,
`make system-e2e-smoke`, `make system-e2e`, and `make system-e2e-soak` are expected
to return nonzero because unimplemented executors are recorded as failures.

## Implemented

- Stable developer commands:
  - `make system-e2e-smoke`
  - `make system-e2e`
  - `make system-e2e-soak`
  - `make system-e2e-plan`
  - `make system-e2e-check`
  - `SYSTEM_E2E_RUN_ID=<run-id> make system-e2e-clean`
- Dedicated `scripts/system_e2e.py` orchestrator.
- Random 24-hex-character run IDs and private `0700` evidence directories.
- Immutable candidate and fixture image-ID validation.
- Random loopback host ports and a run-specific Docker network.
- Exact ownership labels for containers, networks, and volumes.
- Cleanup on success, failure, SIGTERM, and Ctrl-C without Docker prune.
- Private mounted candidate configuration file, deleted during cleanup.
- Source commit, dirty-state digest, seed, manifest hashes, timings, and artifact
  paths in the JSON evidence report.
- Coverage ledger, JSON report, JUnit XML, HTML summary, container logs, baseline
  probes, and replay metadata.
- Frozen OpenAPI inventory discovery and exact 178-operation drift check.
- Dashboard route discovery and reviewed 50-route digest.
- Explicit applicability decisions for 34 classes across all operations:
  - 6,052 operation/class cells.
  - 4,704 executable cells.
  - 1,348 reviewed `not_applicable` cells with rationales.
- Runtime-setting contract for 51 settings, each mapped to positive and
  invalid-value scenarios.
- All 15 required higher-order packs represented by executable scenario records.
- Deterministic constrained pairwise generator:
  - Fixed seed `8675309`.
  - 22 axes.
  - 2,792 valid value pairs.
  - 64 generated rows proving complete valid-pair coverage.
- Scenario-to-feature mapping and expected-evidence validation for all 4,935
  generated scenarios.
- Exact, expiring approval schema with stale-approval validation. There are no
  current checked-in approvals.
- One fixture image with ten one-profile-per-container definitions:
  - REST 1 and REST 2.
  - GraphQL 1 and GraphQL 2.
  - SOAP 1 and SOAP 2.
  - Native gRPC 1 and gRPC 2.
  - Binary gRPC-Web 1 and text gRPC-Web 2.
- Fixture health, deterministic reset, journals, counters, latency, disconnect,
  malformed-response, and status-sequence controls.
- Fixture OpenAPI, Swagger, WSDL, GraphQL, REST, SOAP, gRPC, and gRPC-Web baseline
  behavior.
- Digest-pinned Python fixture base image and pinned Python dependencies.
- Memory candidate startup with encrypted snapshot volume, backend liveness and
  readiness checks, and dashboard HTTP readiness.
- Baseline API/endpoint onboarding and gateway probes for all ten profiles.
- Release checker requires `SYSTEM_E2E_REPORT` and rejects:
  - Non-comprehensive or failed reports.
  - Planned rather than passed topologies.
  - Missing/skipped/failed scenarios.
  - Incomplete operation, pair, or UI coverage.
  - Infrastructure errors or product failures.
  - Invalid candidate image IDs.
  - Reports generated from stale manifests.
- Local/manual invocation only. No system-suite CI schedule or pull-request job was
  added.

## Not implemented yet

### Highest-priority blocker

`Runtime.record_unimplemented_corpus()` currently emits an
`executor-not-implemented` failure for every generated scenario. Replace this with
real domain executors and result aggregation. Never convert missing execution into a
skip or pass.

### Runtime topologies

- External topology:
  - Three-node MongoDB replica set.
  - Authenticated Redis.
  - Digest-pinned Toxiproxy between Doorman and both dependencies.
  - Dependency readiness and health-history recording.
- Two-node topology:
  - Two containers using the identical candidate image ID.
  - Shared MongoDB and Redis.
  - Local round-robin proxy.
  - Direct node-A and node-B addresses.
  - Node-specific service evidence.
  - Cross-node mutation, revocation, cache, and counter assertions.
- Topology-specific teardown verification and leak checks.

### Scenario executors

- Frozen OpenAPI operation executor for every applicable positive and negative
  class, including exact response, state, audit, and redaction assertions.
- Persona seeding and complete identity/authorization lifecycle executor.
- REST, GraphQL, SOAP, native gRPC, and gRPC-Web protocol executors.
- Discovery/import executors for OpenAPI, Swagger, WSDL, GraphQL, proto upload,
  and reflection.
- Runtime-setting positive/invalid/restart/hot-reload executor.
- Pairwise policy-case executor.
- All 15 higher-order pack executors.
- Storage, snapshot, autosave, restart, and restoration executor.
- Observability, analytics, logging, metrics, and audit executor.
- Resilience/performance executor with exact retry and circuit-breaker assertions.

### Browser suite

- Pinned Playwright and Chromium fixture.
- Real-backend workflows for all 50 actionable routes.
- Desktop workflows plus mobile login/navigation/onboarding smoke.
- Console, failed-request, hydration, keyboard, and accessibility assertions.
- Traces, screenshots, videos on failure, and Playwright HTML report.
- Direct HTTP verification of UI mutations and browser verification of API-side
  mutations.

### Soak and chaos

- Five-minute warmup plus 55-minute deterministic workload.
- At least 20 concurrent virtual users and the required protocol percentages.
- Gateway-A restart, Redis outage, MongoDB primary stepdown, upstream faults,
  policy mutation, token revocation, and snapshot/autosave fault schedule.
- Recovery, unexpected-response, divergence, RSS, and fitted-growth assertions.

### Evidence improvements

- JUnit grouping by domain and topology rather than the current flat failure list.
- Per-scenario resolved-input replay rather than only whole-profile replay.
- Per-topology reports and health history.
- Complete scenario result records, not only failures.
- Container metadata export with a secret scan.
- Automated recursive secret scanning across every retained artifact.
- Cancellation and forced-failure integration tests against real Docker resources.

## Recommended pickup order

1. Implement a reusable topology context and the external topology.
2. Add the two-node topology and proxy before writing cross-node executors.
3. Introduce a scenario-result type and replace `record_unimplemented_corpus()`
   incrementally, one executor domain at a time.
4. Complete operation-level control-plane coverage first because it seeds and
   validates most later domains.
5. Add protocol and discovery executors, then pairwise and higher-order packs.
6. Add the pinned Playwright container and browser workflows.
7. Add lifecycle, resilience, storage, and multi-node fault executors.
8. Add the soak scheduler and resource-growth calculations.
9. Expand report generation, artifact secret scanning, replay, and forced-cleanup
   tests.
10. Run smoke until clean, then comprehensive, then soak. Only after all three are
    real and complete should a comprehensive report be supplied to `release-check`.

## Verification completed at this checkpoint

- `python3 -m unittest discover -s scripts -p 'test_*.py'`: **28 tests passed**.
- Focused `scripts.test_system_e2e` and `scripts.test_release_check`: **8 tests
  passed** after the final changes.
- `python3 scripts/system_e2e.py --check`: **passed** with 178 operations, 50 UI
  routes, 2,792 valid pairs, and 4,935 scenarios.
- Python compilation checks: **passed**.
- `git diff --check`: **passed**.
- Fixture Docker image build: **passed**.
- Live fixture container startup and `/health` response: **passed** for the REST 1
  profile.
- Ruff was not available in the environment, so no Ruff result was recorded.

## Important implementation notes

- The worktree was already dirty when this work began. Preserve unrelated changes.
- The existing `.github/workflows/ci.yml` modification predates this system-suite
  work; no system-suite CI invocation was added here.
- Do not weaken the release checker or mark incomplete work as an approved product
  difference. Harness omissions are harness failures.
- The baseline gRPC-Web route currently exercises Doorman's local CRUD behavior;
  the full executor must explicitly determine and report whether advertised upstream
  forwarding matches the product contract.
- The fixture image used for the live verification was tagged
  `doorman-system-fixture-check:local`; its temporary verification container was
  removed. The local image tag may remain in Docker's image cache.
- Evidence directories are ignored by Git under `system-e2e-evidence/`.

