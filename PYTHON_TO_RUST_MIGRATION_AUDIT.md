# Python-to-Rust Migration Audit and Incremental Handoff

Audit date: 2026-08-15
Rust branch/commit audited: `rust-rewrite` at `9f7c05d`
Declared Python parity baseline: `python-parity-reference` at `10699820f50abe3940134536a98c955deab6959f`
Later Python line also reviewed: `origin/main` at `1bb62c1`

This document is the working ledger for completing the Doorman Python-to-Rust migration. Every substantive item has a stable `MIG-###` identifier, a classification, evidence, remaining work, and a definition of done. Future work should update the item in place rather than creating an unrelated checklist.

### Current continuation (2026-09-13)

The executive findings and verification table below describe the original August
audit, not the current worktree. The user reconfirmed a complete v2 backend
switch with 1:1 Python behavior. The pinned reference remains `10699820` with
the previously approved security differences; full operation-level parity and
data-transition evidence remain required.

The current pass restores compilation and formatting, fixes environment-locked
localhost policy and saved proxy trust in login limiting, restores dashboard
security metadata, verifies autosave configuration updates, validates atomic
HTTP timeout/retry reloads, and redacts nested structured log-export credentials.
The live differential identified and corrected the platform CORS credentials
default (Python enables it by default). A real Python-written DMP1 snapshot
then exposed an unsupported tagged-byte password representation: Rust could
decrypt the snapshot but users could not log in. The login decoder now accepts
Python tagged bytes as well as MongoDB binary and rejects malformed encodings;
the focused restore-and-login regression passes.
Configuration import now follows Python upsert behavior rather than replacing
unrelated records; its snapshot and reads occur within the same memory lock or
MongoDB transaction. BSON ObjectIds survive lookup, update, import, and rollback.
Focused tests and the seven real external-store tests pass, including the new
data-preservation assertions. Following the snapshot/restore and security-file
persistence passes, the ledger is 340 covered, 11 approved changed, 40 approved
obsolete, and 209 missing.
No 100% or release-ready claim is made.

The current control-plane follow-up restores FastAPI's malformed JSON envelope
before authentication for shared typed entity and subscription mutations, and
restores Python's target-user group check for subscribe/unsubscribe. Focused
native Rust regressions pass. The generic model-validation and authorization
matrices remain open.

Gateway forwarding now sanitizes allowed header values, applies Python's
truncation behavior, and excludes sensitive configured headers. Focused unit
and local-upstream regressions pass; protocol-wide header behavior remains open.

The 2026-09-14 local continuation verified Python-created snapshot login and
configuration recovery, Rust shutdown/restart and container-replacement recovery,
and a Rust-written snapshot read by a fresh pinned Python process. The tested
synthetic data includes five configuration collections, existing identifiers,
and a Rust-written group. The complete data-transition gate remains open.
See the implementation plan's local evidence section for the candidate digest,
artifact paths, test scope, and the distinction from newer shared-worktree edits.

**User-confirmed launch decision:** Assume no existing v1 users or live v1
deployment. V2 requires a fresh login; Python session continuity is explicitly
out of scope, and issuer/audience validation stays enforced without a legacy
token mode. Python remains the functional parity reference. Existing legacy
data-transition evidence is retained, but continuity of a live v1 installation
is not a launch dependency; v2 persistence and recovery remain release gates.

## 1. How to read this audit

The classifications are deliberately strict:

- **Verified 1:1 slice** means the specifically described behavior is backed by a frozen Python wire fixture, a Python-created artifact, or a focused compatibility test that currently passes. It does **not** imply that the entire surrounding subsystem is at parity.
- **Partially migrated** means a native Rust implementation exists, but one or more Python behaviors, validations, side effects, response shapes, storage modes, or tests are absent or different.
- **Not migrated** means the Python behavior has no effective Rust equivalent.
- **Post-baseline not migrated** means the behavior exists on the later Python `origin/main` line but is outside the repository's pinned parity baseline. Product ownership must decide whether v2 targets the pinned baseline or the later Python product.
- **Verification blocker** means the implementation cannot currently pass the repository's own acceptance gates, or the gate does not prove what its name suggests.

Priorities:

- **P0:** blocks a trustworthy build, frozen contract, security invariant, or baseline decision.
- **P1:** material user-visible or production behavior required for migration completion.
- **P2:** important completeness, operability, or test-depth work.
- **P3:** structural cleanup after behavior is protected.

## 2. Executive findings

1. The runtime cutover itself is complete: Rust owns `/api/*`, `/platform/*`, `/grpc-web/*`, and `/metrics`; there is no Python subprocess proxy or fallback in the current router or container architecture.
2. The declared Python baseline contains 136 OpenAPI paths, 178 operations, 60 schemas, 216 operation parameters, 151 unit-test files, 53 live-test files, and 8 frozen wire contracts. `make parity-reference` passes and verifies those counts.
3. The checked-in Rust source is 18,756 lines. The pinned non-test Python backend is approximately 42,625 lines. Line counts are not a completion metric, but the reduction is consistent with large Python service/model layers having been replaced by a 6,111-line dynamic platform dispatcher and raw `serde_json::Value` documents.
4. Rust has 180 statically declared tests. The pinned Python suite contains 518 unit-test functions plus 82 live-test functions across 204 test files. Only a small subset has a named Rust equivalent.
5. The frozen OpenAPI document is served verbatim from `parity/openapi/python-openapi.json.gz.b64`. The OpenAPI parity test recounts that embedded document; it does not prove that the Rust handlers implement those operations or schemas.
6. Executable cross-runtime parity is narrow: 8 frozen contracts and 8 differential scenarios, mostly health, unauthorized, preflight, missing credentials, and unknown-route cases. That is not enough to claim 178-operation parity.
7. Current acceptance gates are red. The all-target test build does not compile, formatting and Clippy fail, the frozen cache-preflight contract fails, and several integration targets fail.
8. The original migration plan only moved `/api/*` and explicitly kept `/platform/*` in Python. The delivered branch removed Python and also reimplemented the control plane. Most incompleteness is in this unplanned control-plane expansion.
9. The pinned parity commit is not the final Python product line. Relative to it, `origin/main` changes 99 backend files with roughly 8,135 insertions and 1,653 deletions, adding host routing, an API-builder persistence surface, triggers, indexes, realtime updates, OIDC/JWKS, anonymous/scoped access, API-key expiry, a rules engine, and more. Those features are not represented by `parity/reference.json`.
10. There is no defensible single “migration percentage” yet. Establishing an executable 178-operation matrix is a P0 prerequisite to reporting one.

## 3. Current verification snapshot

These results were reproduced from the audited commit using `CARGO_TARGET_DIR=/tmp/doorman-migration-audit-target` where applicable.

| Gate | Result | Meaning |
|---|---:|---|
| `make parity-reference` | Pass | The pinned ref, requirements hash, OpenAPI counts, test-file counts, and fixture count are internally consistent. |
| `cargo test --lib --locked` | 81 passed | Focused library behavior is healthy. |
| `cargo test --test platform_native --locked` | 13 passed | The covered native platform happy paths and guards pass. |
| `cargo test --test runtime --locked` | 20 passed, 1 failed | Cache preflight returns 403 instead of the frozen 204 contract. |
| `cargo test --test parity_contracts --locked` | Failed | `gateway_caches_preflight` differs from the frozen Python fixture. |
| `cargo test --test auth_rate_parity --locked` | Failed | Sixth login request is 400, not the expected 429, in the in-process test configuration. |
| `cargo test --test live_tests_parity --locked` | 5 passed, 2 failed | User onboarding and user-rate-limit scenarios fail. |
| `cargo test --test python_parity_suite --locked` | 3 passed, 1 failed | Chaos state leaks into the GraphQL scenario; GraphQL passes when run alone. |
| `cargo test --locked -- --list` | Compile failure | `tests/openapi_parity.rs` indexes a `Result<Value, _>` instead of unwrapping it. |
| `cargo fmt --all -- --check` | Failed | Multiple Rust files are not rustfmt-clean. |
| `cargo clippy --all-targets --all-features -- -D warnings` | Failed | At least `clippy::match_result_ok` fails in `routes/platform.rs`; later errors may be masked. |
| External MongoDB/Redis integration | Not exercised | Current Rust integration tests use memory/in-process state. |
| Differential Python-vs-Rust run | Not reproducible from the Rust-only image alone | It requires separately starting the pinned Python server and Rust server. No report is checked in. |
| Performance/rollback gates | No checked-in evidence | The original plan's throughput, p95/p99, and rollback acceptance criteria are not demonstrated. |

The pre-existing `.env.example` worktree modification was not changed by this audit.

## 4. Verified 1:1 slices

### MIG-001 — Public health wire contract

- **Classification/Priority:** Verified 1:1 slice / P0 protected behavior.
- **Python source:** `backend-services/routes/gateway_routes.py`; frozen `parity/contracts/fixtures/health_public.json`.
- **Rust source:** `gateway-rs/src/routes/operations.rs`, routed by `gateway-rs/src/app.rs`.
- **Evidence:** `GET /api/health` returns status 200 and `{"status":"online"}` without storage or a legacy backend. The library/runtime test for this behavior passes.
- **Keep it done:** Preserve exact status, body, headers, and availability without policy storage. Any change requires an intentional contract update against the Python oracle.

### MIG-002 — DMP1 memory snapshot cryptographic compatibility

- **Classification/Priority:** Verified 1:1 slice / P0 protected behavior.
- **Python source:** `utils/memory_dump_util.py`, `routes/memory_routes.py`.
- **Rust source:** `gateway-rs/src/storage/snapshot.rs`, `gateway-rs/src/routes/platform.rs`, `gateway-rs/src/main.rs`.
- **Evidence:** Rust decrypts a hard-coded dump generated by Python, uses the compatible HKDF/AES-GCM DMP1 format, accepts the administrator-configured absolute or nested-relative dump paths used by the Python baseline, restores memory collections, supports autosave, SIGUSR1 dump, and shutdown dump.
- **Data-transition finding (2026-09-13):** Cryptographic compatibility did not imply usable restored users. Python encodes password bytes as `{"__type__":"bytes","data":"<base64>"}`; the login decoder now supports that representation with a restore-and-authentication regression test. Keep the cryptographic slice distinct from complete data-transition parity.
- **Snapshot/restore parity pass:** Startup now uses Python's latest matching stem/default-directory search, while the management restore endpoint reads only the exact requested file. Directory hints (with or without a slash), default fallback, case-insensitive .bin extensions, modification-time ordering, missing files, wrong keys, and tampering have focused tests. Key length uses Python character counts. The HTTP harness verifies permission denials, configured/missing/short key responses, custom paths, 404 without fallback, and user recovery; 14 pinned tests gained assertion-level mappings.
- **Keep it done:** Retain a checked-in reverse-direction fixture (Rust dump read by pinned Python) before changing serialization or key derivation. Non-password tagged-byte consumers, path normalization across deployment layouts, and the complete signal/background-task lifecycle matrix still need coverage. Historical image rehearsals predate this source change and must be repeated for the final candidate.

### MIG-003 — API create/update Pydantic compatibility slice

- **Classification/Priority:** Verified 1:1 slice / P1 protected behavior.
- **Python source:** `models/create_api_model.py`, `models/update_api_model.py`, `routes/api_routes.py`.
- **Rust source:** `gateway-rs/src/platform_contract.rs`, `gateway-rs/src/routes/platform.rs`.
- **Evidence:** Passing `platform_native` coverage asserts Python-like defaults, coercion, ignored unknown fields, null removal on update, duplicate handling, credentialed-CORS validation, and FastAPI/Pydantic-style validation errors.
- **Boundary:** This only covers API create/update normalization. It does not cover all API service side effects or other control-plane models.
- **Keep it done:** Every new API field must be added to create, update, response, storage, gateway-policy, OpenAPI-schema, and differential tests together.

### MIG-004 — Request-ID and basic compatibility envelope slice

- **Classification/Priority:** Verified 1:1 slice / P1 protected behavior.
- **Python source:** `utils/correlation_util.py`, `utils/response_util.py`, response middleware in `doorman.py`.
- **Rust source:** `middleware/request_id.rs`, `middleware/response_compat.rs`, platform response helpers.
- **Evidence:** Focused tests cover caller-supplied request IDs, dual `request_id`/`x-request-id` response headers, strict-envelope message wrapping, and probe shape.
- **Boundary:** Error codes and payload shapes are not comprehensively mapped across all 178 operations; see MIG-048.

### MIG-005 — Python-compatible metrics persistence format

- **Classification/Priority:** Verified 1:1 slice / P2 protected behavior.
- **Python source:** `utils/analytics_aggregator.py`, `utils/enhanced_metrics_util.py`, `utils/metrics_util.py`.
- **Rust source:** `observability/analytics_aggregator.rs`, `observability/metrics.rs`, `main.rs`.
- **Evidence:** Rust library tests load/save the Python-compatible metrics file format and render compatible metric names. Startup restore, timed autosave, and shutdown persistence are implemented.
- **Boundary:** Platform analytics query semantics and multi-node aggregation are partial; see MIG-039.

### MIG-006 — Focused route resolution, routing, and transform semantics

- **Classification/Priority:** Verified 1:1 slices / P1 protected behavior.
- **Python source:** `utils/api_resolution_util.py`, `utils/routing_util.py`, `utils/transform_util.py`, `services/gateway_service.py`.
- **Rust source:** `gateway/resolution.rs`, `gateway/routing.rs`, `gateway/transforms.rs`, `routes/rest.rs`.
- **Evidence:** Passing library tests cover path/header version resolution, Python-style path parameters, client routing precedence, round-robin selection, JSON array-path transforms, query transforms, response status transforms, and header swapping. Frozen fixtures exist for REST happy path, not-found, route precedence, request ID, and round-robin state.
- **Boundary:** The full frozen-contract target currently stops on MIG-068 before all fixtures can be trusted as a green gate.

### MIG-007 — Native Rust ownership with no hidden Python fallback

- **Classification/Priority:** Completed migration foundation / P0 protected architecture.
- **Original plan:** `.codex/rust-migration/documents/gateway-rust-v2-plan.md` expected Rust to proxy `/platform/*` to Python.
- **Rust source:** `gateway-rs/src/app.rs`, current Dockerfiles and Compose files.
- **Evidence:** Runtime tests prove `/api/*` and `/platform/*` are handled without an internal or alternate backend. The route tree has no legacy process proxy.
- **Boundary:** This proves ownership, not semantic parity. Reintroducing a fallback would hide missing behavior and should not be used to close items below.

## 5. Partially migrated baseline behavior

### MIG-008 — Baseline governance and migration scope

- **Classification/Priority:** Partially migrated / P0.
- **Problem:** The original plan's scope and the delivered scope differ materially. It also says “implementation in progress” while README now claims unchanged public contracts and a complete native control plane.
- **Remaining work:** Choose and record one target: (a) exact pinned commit `10699820`, or (b) the later Python `origin/main` product. Define whether intentional security changes such as private registration/docs are accepted divergences.
- **Done when:** `parity/reference.json`, the migration plan, README claims, CI, and the operation ledger all point to the same baseline and list every approved divergence with rationale and tests.

### MIG-009 — OpenAPI must describe executable Rust behavior

- **Classification/Priority:** Partially migrated / P0.
- **Python source:** FastAPI-generated `/platform/openapi.json`.
- **Rust source:** `platform.rs::platform_openapi`, which decodes and serves the frozen Python document.
- **Gap:** The test in `tests/openapi_parity.rs` fetches the embedded Python document and recounts it. A handler can be missing or behaviorally incompatible while the test still reports 136 paths and 178 operations.
- **Remaining work:** Generate OpenAPI from typed Rust route definitions or maintain a machine-readable route-to-operation registry. Validate every document operation against an executable handler/method and validate response/request schemas with representative cases.
- **Done when:** CI fails for an undocumented handler, documented nonexistent handler, missing method, or schema drift; it must not merely hash/count the frozen artifact.

### MIG-010 — Monolithic platform dispatcher and method coverage

- **Classification/Priority:** Partially migrated / P1.
- **Python source:** 30 top-level route modules and 14 service modules.
- **Rust source:** `gateway-rs/src/routes/platform.rs` (approximately 6,111 lines).
- **Current behavior:** The frozen route strings are broadly represented through exact matches, prefix matches, and generic entity routing.
- **Gap:** A single `any` Axum route accepts all platform methods and performs runtime string dispatch. Compile-time route metadata, extractor validation, method-specific body types, and generated documentation are lost. Prefix logic can accidentally accept undocumented aliases or route a documented path to generic behavior.
- **Done when:** Split by domain, register exact Axum methods, reject unsupported methods consistently, and bind every frozen OpenAPI operation to one handler-level contract test.

### MIG-011 — Control-plane request/response model validation

- **Classification/Priority:** Partially migrated / P0.
- **Python source:** 36 Python model modules under `backend-services/models/`, predominantly Pydantic request/response types.
- **Rust source:** `platform_contract.rs` only types API create/update; most other handlers accept raw `serde_json::Value`.
- **Gap:** Tiers, credits, vault entries, subscriptions, endpoint-validation models, and remaining error-location detail do not consistently enforce Python field types, defaults, min/max lengths, enum values, item counts, and unknown-field policy.
- **Current boundary:** User, role, group, routing, and endpoint create/update models now have explicit compatibility normalizers with focused positive/negative request regressions. The generic role/group/routing handlers no longer accept their prior raw JSON surface.
- **Done when:** Each Python create/update/request model has a Rust type or explicit compatibility normalizer and positive/negative differential tests for defaults, coercion, null, unknown fields, bounds, enums, and error envelopes.

### MIG-012 — Login, JWT, cookies, refresh, and status

- **Classification/Priority:** Partially migrated / P0.
- **Python source:** `routes/authorization_routes.py`, `utils/auth_util.py`, `utils/key_util.py`.
- **Rust source:** `routes/platform.rs`, `policy/auth.rs`, `config.rs`.
- **Implemented:** bcrypt login, email/username lookup, active-user checks, HS256/RS256 key selection and `kid`, issuer/audience verification, access cookies, CSRF token storage, refresh, status, invalidate, and admin controls.
- **Cookie/JWT follow-up:** Isolated Rust child-process login tests now cover Python's default Strict/non-Secure cookies, `COOKIE_SAMESITE=Lax`, the non-Secure `SameSite=None` downgrade, HTTPS_ONLY Secure `SameSite=None`, and the host-only `testserver` outcome of `COOKIE_DOMAIN`. A valid-looking token signed with a different HS256 key returns HTTP 401 `AUTH003`. These five pinned cases are mapped in the ledger; the full 46-test native platform suite passes.
- **Current wire evidence:** A fresh pinned-Python login/refresh/status sequence establishes that status returns exactly `{"message":"Token is valid"}` and refresh exposes only `refresh_token` while setting seven-day CSRF/access cookies. Rust now returns those same bodies and its native regression asserts them exactly.
- **Gaps:** Rust token claims omit Python's embedded `accesses` permission object. Refresh reloads the current persisted role, malformed login JSON returns `AUTH004`, and both login/refresh cookie lifetimes now use their computed token expiry. A live cross-runtime check confirms existing Python sessions are rejected by Rust because the Python tokens lack the issuer/audience claims Rust requires. Restored-user login succeeds. Cookie lifetime, inactive-user, configured issuer/audience/kid rotation, and direct/proxy authentication matrices remain incomplete.
- **Approved session policy:** The user requires fresh login and directs us to assume no existing v1 users. Python session rejection is intentional for v2; no legacy-token compatibility mode is required, and issuer/audience validation remains unchanged. This decision does not approve other authentication response or permission differences.
- **Done when:** Port `test_auth*`, cookie, JWT config/key rotation, refresh, malformed JSON, and permission-claim cases; compare exact cookies, claims, statuses, headers, and bodies.

### MIG-013 — Token revocation lifetime and auth rate limiting

- **Classification/Priority:** Partially migrated / P0.
- **Python source:** `utils/auth_blacklist.py`, `utils/ip_rate_limiter.py`, authorization routes, lifespan purger.
- **Rust source:** `routes/platform.rs::authorize`, `authorization_routes`, `auth_ip_rate_limit`, storage runtime.
- **Implemented:** Per-JTI and revoke-all records, invalidation, admin revoke/unrevoke, account/IP windows, and shared storage counters.
- **Gaps:** Rust intentionally persists external revocations as collection documents rather than Python's Redis key/TTL implementation; it now ignores and deletes expired records. Focused memory and isolated two-instance MongoDB/Redis tests verify rejection, expiry cleanup, and shared state. The rate-limit parity target does not rate-limit in-process requests under default trusted-proxy settings (MIG-069).
- **Done when:** Expired records stop revoking, purge/TTL behavior works in memory and external mode, cross-node behavior is tested, and login/register account/IP limits match Python wire headers and messages under an explicit proxy trust model.

### MIG-014 — User lifecycle and authorization guards

- **Classification/Priority:** Partially migrated / P0.
- **Python source:** `routes/user_routes.py`, `services/user_service.py`, create/update/password models.
- **Rust source:** `platform.rs::user_routes`, `create_user`, `user_by`.
- **Implemented:** CRUD, password hashing/policy, uniqueness, public-field masking, own-user reads, custom-attribute count, role-escalation checks, admin protection, and password update.
- **Verified current behavior:** The current live onboarding fixture creates the `developer` user successfully, and the administrator self-update path permits the bootstrap admin's operational rate/throttle fields. `live_test_10_user_onboarding_lifecycle_parity` and `live_test_33_rate_limiting_blocks_excess_requests_parity` both passed on 2026-09-18; the prior audit claim that these scenarios failed was stale.
- **Current model evidence:** Fresh pinned-Python user-create and user-update oracles confirm required-role validation, required-field/length/negative-limit failures, scalar string/integer/boolean coercion, list-item coercion, the `bandwidth_limit_window="day"` default, empty-list custom-attribute coercion, ignored unknown fields, and update null-elision. Rust now normalizes and regression-tests those observed create/update model boundaries.
- **Role-change side effect:** Python's `UserService.purge_apis_after_role_change` examines the legacy API `role` allowlist (not the normal create-model `api_allowed_roles` field) after a role update. Rust mirrors that transition, including Python's in-place list-removal iteration behavior; storage writes invalidate the shared policy cache. Native and isolated two-connection MongoDB/Redis regressions cover the transition, persisted cleanup, and policy-cache refresh.
- **Gaps:** Remaining model corners (large/scientific numeric forms and every nested value shape) and the exact Python cache-key lifecycle are incomplete. The broader user route/service guard matrix remains unproven.
- **Done when:** Port all user route/service guard tests, verify cache invalidation, and exercise lifecycle behavior in memory and external storage without weakening privilege protections.

### MIG-015 — Roles and groups

- **Classification/Priority:** Partially migrated / P1.
- **Python source:** role/group routes, services, models, `utils/role_util.py`, `utils/group_util.py`.
- **Rust source:** generic `entity_routes`, `policy/roles.rs`, `policy/groups.rs`.
- **Implemented:** CRUD, pagination, RBAC checks, protected `admin`/`ALL`, non-escalation guard, and data-plane role/group intersection. Role/group create and update now normalize the observed Pydantic boundaries: scalar coercion, known-field selection, create defaults, nullable-field elision, bounds, list-item coercion, and empty-update failures. Native regression coverage verifies those transitions.
- **Gaps:** Delete/update effects on users and cached policy documents are not behaviorally compared. Error codes/messages and response bodies are generic in several branches. The generic handler does not prove Python's role/group not-found and permission matrices or external lifecycle behavior.
- **Done when:** Port model validation and all positive/negative role/group CRUD, assignment, deletion, and enforcement tests in memory and external mode.

### MIG-016 — Client routing management and state

- **Classification/Priority:** Partially migrated / P1.
- **Python source:** routing routes/service/utilities and gateway selection logic.
- **Rust source:** generic routing entity handler, `gateway/routing.rs`, `storage/runtime.rs` Lua/state paths.
- **Implemented:** CRUD shell, client-key precedence, endpoint/API fallback, and round-robin state with focused tests. Create/update request handling now follows the routing Pydantic models for generated client keys, known fields, scalar/list coercion, server-list cardinality, string bounds, default/nonnegative server index, null elision, and the update model's excluded `server_index` field.
- **Gaps:** Full header swap, cache reset, concurrency, external Redis, and update/delete invalidation matrices are not ported. Several route/service error codes and response shapes still use the generic handler.
- **Done when:** Every routing model/service test and live routing/header-swap case is represented, including atomic multi-instance round-robin tests.

### MIG-017 — API lifecycle beyond model normalization

- **Classification/Priority:** Partially migrated / P1.
- **Python source:** `routes/api_routes.py`, `services/api_service.py`, API models.
- **Rust source:** `platform.rs::api_routes`, `platform_contract.rs`.
- **Implemented:** create/list/get/update/delete, defaults, duplicates, paging, active flag, proto metadata merge, and policy-cache invalidation through storage writes.
- **Gaps:** Service-level cascade behavior, endpoint cleanup, validation for every protocol-specific field, mask/response semantics, cache key compatibility, and all failure modes are not fully ported. Rust accepts `api_openapi_schema` in normalization but discovery reads `api_openapi_spec`, leaving an internal field mismatch.
- **Done when:** Build a field-by-field matrix for create/update/response models and port API active/patch, CRUD failures, by-name/version, CORS, proto, cache, and deletion side-effect tests.

### MIG-018 — Endpoint and endpoint-validation lifecycle

- **Classification/Priority:** Partially migrated / P1.
- **Python source:** endpoint routes/service and endpoint/validation models.
- **Rust source:** `platform.rs::endpoint_routes`, `validation/json.rs`, `validation/xml.rs`, protocol request validation in `routes/rest.rs`.
- **Implemented:** endpoint CRUD, validation-schema CRUD aliases, endpoint lookup, JSON nested fields/types/ranges/formats/custom validators, GraphQL variable scoping, SOAP body extraction, and gateway enforcement. Endpoint create/update now normalizes the Pydantic fields (known-field selection, scalar/list coercion, required/optional bounds, and update null-elision) with a request-level regression.
- **Lifecycle evidence:** Endpoint creation now rejects a missing API, derives `api_id` from the persisted API, overwrites request identifiers, preserves Python's stored `client_uri: null` default, and rejects duplicate endpoint or client-URI collisions. Updates preserve route identity, reject no-ops and client-URI collisions, and deletion now has the source-specific missing-record contract. Native coverage exercises each result; the isolated MongoDB/Redis endpoint restart suite also passes.
- **Gaps:** Cache/cascade behavior and proto pre-generation behavior differ by architecture and lack equivalence tests. Schema validation semantics are a custom subset, not a complete Python model/schema implementation; protobuf validation is a one-line shell.
- **Done when:** Port endpoint CRUD failures, validation CRUD, edge cases, builder protocols, and exact error shapes; document intentionally unsupported schema keywords.

### MIG-019 — Subscriptions

- **Classification/Priority:** Partially migrated / P1.
- **Python source:** subscription routes/service/utilities and subscribe model.
- **Rust source:** `platform.rs::subscription_routes`, `policy/subscription.rs`.
- **Implemented:** subscribe/unsubscribe, self/admin reads, available APIs, duplicates/not-subscribed errors, and data-plane enforcement with admin bypass option. The subscribe model now strips unknown fields, applies Python-compatible scalar-to-string coercion, enforces the username/API/version bounds, and returns the source validation envelope before authorization.
- **Gaps:** Rust's available-API calculation returns all APIs rather than proving Python eligibility filtering. Response shape includes compatibility duplication (`apis` and nested `subscriptions`). User existence, active state, public API behavior, cache invalidation, and complete permission/error matrices are not compared.
- **Done when:** Port all subscription service/route/live tests and differential state-transition cases.

### MIG-020 — Credits and upstream key injection

- **Classification/Priority:** Partially migrated / P1.
- **Python source:** credit routes/service/utilities/models.
- **Rust source:** `platform.rs::credit_routes`, `policy/credits.rs`, `storage/runtime.rs::deduct_credit`, `routes/rest.rs`.
- **Implemented:** definition CRUD, user overrides, key rotation, availability check, upstream system/user API-key injection, and atomic-looking Mongo decrement with memory equivalent. Credit-definition and user-credit writes now enforce the required Python model fields, tier/user-credit nested shapes, Pydantic-style scalar coercion, string bounds, and unknown-field elision before authorization; direct Rust coverage records the normalized persisted state and invalid envelopes.
- **Gaps:** Date-time coercion for key-rotation expiry, masking, tier reset semantics, rotation semantics, input/output limits, reset scheduling, exact failure envelopes, and all concurrent external-store cases are unverified. The ported live test checks storage CRUD only, not successful upstream deduction and failure rollback semantics.
- **Done when:** Port definition masking, rotation, injection/deduction, user override, reset, concurrency, and live public credit tests with before/after storage assertions.

### MIG-021 — Tier CRUD and assignment workflows

- **Classification/Priority:** Partially migrated / P0.
- **Python source:** `routes/tier_routes.py`, `services/tier_service.py`, tier/rate-limit models.
- **Rust source:** generic tier entity CRUD, `platform.rs::tier_management_routes`, `policy/tier.rs`.
- **Implemented:** tier documents, assignment storage, effective dates, overrides, default tier fallback, minute/hour/day enforcement, basic compare, list users, and action endpoints. Assignment create/reassignment now follows `TierService.assign_user_to_tier`: it verifies the tier, replaces (rather than merges) an existing assignment, materializes every `UserTierAssignment.to_dict()` field including nulls, returns the assignment at 201, and reports a missing tier as the Python 400 detail response. Effective-tier lookup now uses Python's default fallback; delete and compare use the Python message/detail and raw-list response shapes. Upgrade, downgrade, temporary upgrade, trial start, and payment failure now replace and return `UserTierAssignment` records with the Python effective-date and notes rules (including the payment-failure default-tier fallback). Tier deletion now protects assigned tiers; user lists use Python pagination/raw-list output; and per-tier/all-tier statistics now supply active/inactive counts including empty tiers. Tier CRUD now uses a dedicated handler that returns normalized `TierResponse` records, idempotent create responses, filtered paging, and Python missing-resource details. Native contract tests cover these behaviors.
- **Pinned defects preserved:** On the live pinned in-memory reference, a nonempty tier search with any tier present crashes because `TierService.list_tiers` calls `.lower()` on `TierName`, producing `500 TIER999`; and effective-tier lookup after assigning serialized effective dates returns `500 {"detail":"Failed to get user tier"}` because the service compares `datetime` to a stored string. The same string-date defect means a successful dated upgrade is followed by `500` responses for downgrade (`Failed to downgrade tier`) and payment failure (`Failed to handle payment failure`). Rust now matches all of these. Fresh authenticated Python/Rust memory-container sequences matched exactly for create, normal list, search failure, update, assignment, effective-tier failure, and chained upgrade/downgrade/payment after normalizing only timestamps/request IDs.
- **Gaps:** Exact Pydantic coercion/error locations and unknown-field policy, cache invalidation, email/notification side effects, externally backed replacement semantics, and differential timestamp/date fixtures beyond the observed failure remain. Compare/statistics/list pagination and CRUD have native behavior coverage but not full external Python/Rust operation fixtures.
- **Done when:** Port tier route/service tests for every one of the 18 OpenAPI operations and assert resulting assignments, time behavior, cache invalidation, and exact responses.

### MIG-022 — Quota status, accounting, and enforcement

- **Classification/Priority:** Partially migrated / P0.
- **Python source:** `routes/quota_routes.py`, `utils/quota_tracker.py`, dormant quota logic in `middleware/rate_limit_middleware.py`.
- **Rust source:** `platform.rs::quota_routes`, unused `policy/quota.rs`.
- **Implemented (2026-09-18):** Quota status now resolves the effective nested tier limits (including default-tier fallback for inactive assignments and user overrides), reads Python-compatible shared tracker counters, and returns calendar reset timestamps, warning/critical/exhaustion thresholds, and the response-only burst fields. Dashboard, specific status, request-only JSON/CSV export, tier info, and burst-status shapes were checked against a pinned Python container. The native regression seeds shared tracker usage and verifies threshold, no-tier, export, and expired-assignment behavior. The existing external storage suite proves the same Redis counter primitive is shared across connections.
- **Nuance:** Python quota history is explicitly a placeholder, and the generic Python `RateLimitMiddleware` containing quota increments does not appear to be mounted in the pinned app. Rust deliberately does not attach `check_quota` to the evaluator until a product decision requires behavior Python does not currently expose.
- **Remaining work:** Exercise the successful quota dashboard through an external MongoDB/Redis router fixture and add a complete-operation differential fixture once production-like tier data is available. Do not treat standalone quota enforcement as parity until the pinned Python middleware is mounted or a product decision explicitly changes that contract.

### MIG-023 — Managed rate-limit rule APIs

- **Classification/Priority:** Partially migrated / P1.
- **Python source:** rate-limit-rule routes/service/models and rate-limiter utilities.
- **Rust source:** `rate_limit_crud_routes` and `rate_limit_management_routes`.
- **Implemented:** raw rule CRUD, search, enable/disable, duplicate, and statistics. The dedicated CRUD path now emits Python's response model/defaults/timestamps, priority-descending raw filtered lists, mutation results, and delete envelope. The pinned source and live container establish that all managed rule endpoints are publicly callable; Rust dispatches that exact surface before platform authorization. `/rate-limits/status` is declared after `/{rule_id}` in Python and is therefore unreachable: both unauthenticated and authenticated calls return `404 {"detail":"Rule status not found"}`. In memory mode, Python's `$regex` search returns an empty successful array; Rust preserves that backend-specific wire defect while retaining the source's ID/description/target priority search for external Mongo. Missing targets for simple targeted rules preserve Python's `Failed to create rule` 500 defect. Statistics returns total/enabled/disabled counts plus all `RuleType` buckets. A live Python container showed that its advertised bulk enable/disable routes are shadowed (`Rule bulk not found`) and bulk delete raises `Failed to delete rules`; Rust deliberately preserves these wire defects.
- **Gaps:** Live create/update checks now cover numeric/boolean strings and values, JSON-float truncation, decimal-string rejection, null-elision, and ignored unknown fields. The full Pydantic negative matrix (large integers, scientific forms, containers across every field, and every error shape) remains incomplete.
- **Nuance:** `doorman.py` mounts `TierRateLimitMiddleware`, not `RateLimitMiddleware`. The latter's `_default_get_rules` also contains a TODO to query MongoDB. Consequently, the pinned management-rule API does not affect gateway traffic; Rust's evaluator deliberately does not read `rate_limit_rules` for the same baseline behavior. The management API still requires wire parity.
- **Done when:** Freeze Python management contracts, decide whether managed rules must be executable, and then add evaluator selection tests for user/API/endpoint/IP/composite/global rule types if required.

### MIG-024 — Per-user rate limit, throttle, bandwidth, and tier enforcement

- **Classification/Priority:** Partially migrated / P0.
- **Python source:** tier middleware, limit/throttle/bandwidth utilities, gateway service.
- **Rust source:** `policy/rate_limit.rs`, `throttle.rs`, `bandwidth.rs`, `tier.rs`, `evaluator.rs`, storage counters.
- **Implemented:** fixed/sliding user windows, tier windows, request bandwidth pre-check, full request/header/response bandwidth accounting, user usage/reset status fields, monitor byte totals, throttle delay/queue checks, Redis-backed shared effects, rate headers, and fail-closed storage errors. All five pinned unit bandwidth cases and the pinned skipped live case have assertion-level Rust mappings using deterministic counters or a real local upstream.
- **Gaps:** Full Python token-bucket/hybrid burst semantics, exact queue/wait concurrency, all headers, retries' interaction with counters/credits, and external multi-node bandwidth accounting are not proven.
- **Done when:** Port all unit/live rate, throttle, bandwidth, tier strict, and public-limit matrices with deterministic clocks and multi-request concurrency.

### MIG-025 — IP policy and trusted proxy behavior

- **Classification/Priority:** Partially migrated / P0.
- **Python source:** `utils/ip_policy_util.py`, security settings, platform filters, login limiter.
- **Rust source:** `policy/ip.rs`, `platform_ip_filter`, authentication limiter, metrics route, config.
- **Implemented:** IPv4/IPv6 CIDR, blacklist/whitelist, local-host bypass hardening, optional forwarding-header trust, saved proxy IP/CIDR allowlists for platform and per-API policy, the security-settings recovery-route exemption, and structured global-denial audit events. All 13 pinned unit and both pinned live IP-policy/filter/login cases have assertion-level Rust mappings; the live cases use a real local REST upstream.
- **IP-pattern follow-up:** The shared matcher now accepts Python-compatible IPv4 dotted netmasks/hostmasks and trims Python whitespace, including ASCII information separators. Numeric CIDR prefixes require unsigned ASCII digits; `/+24` no longer grants an allowlist or proxy match. Two regressions reproduced the old failures and now pass. Unit tests cover allow/deny/proxy outcomes, invalid-only patterns, zero/full masks, and address-family mismatch; authenticated settings updates feed a real request fixture with trusted/untrusted direct-peer context. The cases match `_ip_in_list` extracted from the pinned Python source.
- **Gaps:** Python and Rust production defaults intentionally remain conservative around forwarded headers/local bypass. The shared parser now serves platform, gateway, authentication, and metrics; authentication uses the saved trusted-proxy list. The environment localhost lock is enforced in platform and gateway policy with focused coverage. Metrics retains its separate opt-in trust setting; full proxy-chain and cross-node policy matrices remain open.
- **Done when:** Centralize resolution across platform, metrics, auth, and gateway paths and verify external/proxy-chain behavior without trusting spoofable headers by default.

### MIG-026 — REST proxy execution

- **Classification/Priority:** Partially migrated / P1.
- **Python source:** gateway routes/service, HTTP client, gateway utilities.
- **Rust source:** `routes/rest.rs`, gateway modules, policy evaluator.
- **Implemented:** resolution, policy evaluation, filtered forwarding, query/body/header transforms, timeouts, retries, circuit breaker, compression, body limit, upstream response transforms, activity metrics, and CRUD branch.
- **Gaps:** The frozen set covers only a handful of REST cases. Missing equivalent coverage includes every HTTP method/405 branch, chunked bodies, header matrices, mutating retry behavior, circuit transitions, upstream exception mapping, content types, streaming byte accounting, combinations, and external-state concurrency.
- **Done when:** Port the complete gateway REST test families and live upstream tests, comparing outgoing requests as well as client responses and state changes.

### MIG-027 — GraphQL gateway

- **Classification/Priority:** Partially migrated / P1.
- **Python source:** GraphQL branch in gateway service plus `utils/graphql_util.py`.
- **Rust source:** common proxy in `routes/rest.rs`, `validation/graphql.rs`, `routes/graphql.rs`.
- **Implemented:** JSON proxying, content headers, depth checking, variable validation scoping, original URI preservation, and policy integration.
- **Gaps:** The GraphQL parity integration test is too permissive and is polluted by global chaos state. Full query parsing, named/multiple operation behavior, introspection policy, error/status/envelope mapping, fallback paths, missing version headers, and validation edge cases have not been ported.
- **Done when:** Port all pinned GraphQL unit/live files with isolated state and exact upstream request/response assertions.

### MIG-028 — SOAP gateway

- **Classification/Priority:** Partially migrated / P1.
- **Python source:** SOAP gateway service paths and WSDL utilities.
- **Rust source:** common proxy in `routes/rest.rs`, `protocol/soap.rs`, `validation/xml.rs`.
- **Implemented:** GET/POST routing, SOAP 1.1/1.2 content types, SOAPAction forwarding, WS-Security header injection, DTD/entity rejection when validating, body extraction, retry path, and original URI preservation.
- **Gaps:** Only focused unit and broad live-port tests exist. Envelope/fault mapping, every WS-Security option, schema edge cases, preflight matrices, retries, content-type negotiation, and upstream fault preservation need differential coverage.
- **Done when:** Port all SOAP unit/live tests and freeze upstream SOAP envelopes as fixtures.

### MIG-029 — Native JSON-to-gRPC gateway

- **Classification/Priority:** Partially migrated / P1.
- **Python source:** gRPC paths in gateway service, generated modules, reflection fallback, `utils/grpc_util.py`.
- **Rust source:** `protocol/grpc.rs`, `routes/grpc.rs`, descriptor storage.
- **Implemented:** dynamic descriptors, unary/server/client/bidirectional streaming, metadata propagation, package/service/method allowlists, timeouts, retryable tonic statuses, TLS endpoint normalization, and JSON conversion.
- **Gaps:** Most tests are unit-level helpers, not a real tonic server exercising all modes. Python generated-module fallback/reflection resolution order, exact error branches, TLS certificates/options, deadlines, max-item behavior, metadata, subscription/metrics effects, retries, and package resolution are not proven 1:1.
- **Done when:** Port every pinned gRPC unit and live scenario against real local gRPC servers and compare bodies, HTTP mappings, metadata, counters, and retry attempts.

### MIG-030 — gRPC-Web

- **Classification/Priority:** Partially migrated / P1.
- **Python source:** `/grpc-web/{api_name}/{service}/{method}` and gateway gRPC helpers.
- **Rust source:** `routes/grpc_web.rs`, `protocol/grpc.rs::execute_web_gateway`.
- **Implemented:** binary/text unary frames, text server-streaming output, trailers, descriptor lookup, policy, and allowlists.
- **Gaps:** Client/bidirectional streaming is rejected, as expected for common gRPC-Web clients, and binary server streaming is explicitly unsupported. Exact Python behavior, CORS/preflight, malformed/multiple frames, compression, trailers, metadata, and browser compatibility are not broadly tested.
- **Done when:** Freeze Python gRPC-Web frames and implement a protocol matrix for binary/text unary and server streaming, plus explicit approved divergences.

### MIG-031 — `api_is_crud` protocol builder

- **Classification/Priority:** Partially migrated / P1.
- **Python source:** `services/crud_service.py`, builder tests, gateway CRUD branch.
- **Rust source:** `protocol/crud.rs`, CRUD branch in `routes/rest.rs`, generic CRUD storage methods.
- **Implemented:** REST CRUD, GraphQL operation recognition, SOAP discovery/execution, gRPC discovery/execution scaffolding, schema checks, safe collection names, and generated discovery documents.
- **Gaps:** Recursive/nested schema behavior was already incomplete in Python and remains custom. Full protocol status/error envelopes, filtering/pagination, PATCH semantics, collection naming compatibility, dynamic external collections, and all builder tests are not ported.
- **Done when:** Use pinned builder tests as the executable matrix and add equivalent real requests for REST, GraphQL, SOAP, and gRPC over memory and Mongo.

### MIG-032 — `/api/caches` operations and CORS

- **Classification/Priority:** Partially migrated / P0.
- **Python source:** gateway cache operation and special CORS behavior.
- **Rust source:** `routes/operations.rs`, storage cache clearing.
- **Implemented:** local handling, authorization/permission/CSRF paths, cache clearing, and preflight response builder.
- **Gap:** With no matching `ALLOWED_ORIGINS`, Rust returns 403 for the frozen `https://console.example` preflight while the checked-in Python fixture requires 204 with empty body and CORS headers. This breaks `runtime` and `parity_contracts`.
- **Done when:** Decide whether the frozen contract or newer security policy wins, update only through an explicit approved divergence, and make runtime plus frozen-contract tests green under deterministic environment isolation.

### MIG-033 — Memory and external storage backends

- **Classification/Priority:** Partially migrated / P0.
- **Python source:** database, async DB, Redis client/cache, shared metrics utilities.
- **Rust source:** `storage/memory.rs`, `runtime.rs`, `mongo.rs`, `redis.rs`, `cache.rs`.
- **Implemented:** in-memory collections/counters/ephemeral values, Mongo CRUD/config, Redis counters/cache/revision/routing/analytics writes, policy snapshot caching, health checks, and atomic scripts/updates in several hot paths.
- **Gaps:** Current integration tests do not connect to MongoDB or Redis. BSON edge cases, indexes/uniqueness, reconnect/failure behavior, TTL semantics, transactions, multi-node revisions, rollback partial failure, and memory-vs-Mongo `_id` behavior are unverified.
- **Done when:** Add containerized external-store tests for every stateful policy and control-plane domain, including concurrency and outage recovery.

### MIG-034 — Cache namespaces and invalidation semantics

- **Classification/Priority:** Partially migrated / P1.
- **Python source:** sync/async cache utilities and cache manager.
- **Rust source:** `storage/cache.rs`, `storage/runtime.rs`, policy snapshot revision.
- **Implemented:** Python-compatible prefix enum, expiring in-memory counters, Redis wildcard clear patterns, and policy invalidation after writes.
- **Gaps:** Prefix helpers are not evidence that all Python keys/leading-slash variants are read or cleared. Domain-specific user/role/tier/discovery caches, exact TTLs, failed-write invalidation, and cross-node visibility are not mapped. Discovery in Rust persists documents rather than reproducing Python cache TTL behavior.
- **Done when:** Create a key-by-key compatibility table and tests for create/update/delete, expiry, clear-all, and external multi-node reads.

### MIG-035 — OpenAPI discovery and endpoint import

- **Classification/Priority:** Partially migrated / P1.
- **Python source:** `routes/openapi_routes.py`, API utilities/cache.
- **Rust source:** `routes/discovery.rs`, `platform.rs::api_discovery_routes`, `discovery_parse`.
- **Implemented:** parsing of OpenAPI endpoint metadata, fetch/refresh, host allowlist/SSRF checks, persistence, duplicate skipping, and endpoint import.
- **Gaps:** Refresh accepts only JSON into structured storage and falls back to `{raw: ...}` instead of full JSON/YAML compatibility. Python cache TTL/refresh semantics, authentication to discovery targets, schema/reference handling, server/base-path rules, import field coverage, rollback on partial import, and exact response/error shapes are incomplete.
- **Done when:** Port all OpenAPI route/util tests with JSON and YAML fixtures, references, malformed inputs, SSRF cases, and import state comparisons.

### MIG-036 — WSDL discovery and import

- **Classification/Priority:** Partially migrated / P1.
- **Python source:** WSDL routes/utilities.
- **Rust source:** `routes/discovery.rs`, platform discovery handlers.
- **Implemented:** safe XML parsing, DTD rejection, service/namespace/operation extraction, fetch/refresh, and endpoint import. A native platform test passes without an external service.
- **Gaps:** Complex WSDL imports/includes, bindings, namespaces, SOAP versions/actions, multiple services/ports, endpoint metadata, cache semantics, and exact errors are not fully compared.
- **Done when:** Port pinned WSDL unit/route tests and a fixture corpus covering multi-service and malformed/security cases.

### MIG-037 — GraphQL schema discovery

- **Classification/Priority:** Partially migrated / P1.
- **Python source:** `routes/graphql_routes.py`, `utils/graphql_util.py`.
- **Rust source:** `platform.rs::api_discovery_routes`.
- **Implemented:** stored schema GET, refresh through an introspection request, and type listing.
- **Gaps:** Rust's introspection query requests only type names/kinds and root names, not a full schema. Cache/TTL semantics, auth headers, disabled introspection, full types formatting, errors, and schema validation are not matched.
- **Done when:** Freeze Python schema/type payloads and port all GraphQL discovery tests with authenticated and failing upstreams.

### MIG-038 — Proto upload, descriptor lifecycle, and gRPC discovery

- **Classification/Priority:** Partially migrated / P1.
- **Python source:** `routes/proto_routes.py`, endpoint service proto generation, gRPC routes/utilities.
- **Rust source:** `platform.rs::proto_routes`, `compile_proto`, stored descriptor parsing.
- **Implemented:** multipart/raw proto extraction, safe names, vendored protoc descriptor compilation, source/descriptor digest storage, GET/PUT/POST/DELETE, manual and external-startup backfill, and service listing from descriptors.
- **Gaps:** Python generated-module filesystem behavior is intentionally architecturally different but its observable errors/import fallbacks are not mapped. Rust service discovery uses stored descriptors only; it does not perform upstream reflection fallback. Proto imports/include paths, multiple files, complex packages, cleanup, external storage, and all security tests need coverage.
- **Done when:** Port proto route/security/TLS/package/reflection tests, retain external-startup backfill coverage, and document filesystem behavior as an approved internal divergence.

### MIG-039 — Analytics collection and queries

- **Classification/Priority:** Partially migrated / P1.
- **Python source:** analytics middleware/routes/models, aggregator/scheduler, shared metrics.
- **Rust source:** `middleware/activity.rs`, `observability/analytics_aggregator.rs`, platform analytics handlers, `storage/runtime.rs::record_gateway_metric`.
- **Implemented:** in-process counters/timeseries/top entities, status distribution, persistence, seven query routes, dashboard consumption, and Redis minute-bucket writes.
- **Gaps:** The Redis/shared metric buckets are write-only in Rust; platform analytics reads the process-global aggregator. Multi-instance analytics therefore does not aggregate shared state. Several returned values are placeholders (`avg_ms` and endpoint percentiles are zero; unique users per point is zero). Scheduler/granularity/range semantics, geolocation, test-request exclusion, and model validation are not fully ported.
- **Done when:** Query shared buckets in external mode, port all analytics/metrics range/model tests, and compare exact aggregates across multiple instances and restart.

### MIG-040 — Dashboard, monitor, readiness, and Prometheus operations

- **Classification/Priority:** Partially migrated / P1.
- **Python source:** dashboard, monitor, metrics routes; health utilities and Prometheus metrics.
- **Rust source:** platform dashboard/monitor functions, `routes/metrics.rs`, `observability/metrics.rs`.
- **Implemented:** liveness/readiness, privileged storage detail, dependency and background-task health, fail-closed missing-gRPC-descriptor reporting, basic monitor metrics/report, dashboard shape, protected `/metrics`, and compatible metric names. Focused platform tests pass.
- **Gaps:** Monitor data is substantially simpler, memory/CPU/connection/upstream details and range behavior are incomplete, dashboard values rely on local analytics, and external outage matrices are missing.
- **Done when:** Port all dashboard/monitor/metrics/health edge tests and live readiness scenarios in memory and external modes.

### MIG-041 — Logging, audit, export, and redaction

- **Classification/Priority:** Partially migrated / P0.
- **Python source:** logging middleware/routes/service, audit utility/middleware, sanitize utility, memory log.
- **Rust source:** `middleware/activity.rs`, `observability/logging.rs`, `observability/audit.rs`, `platform.rs::logging_routes`; unused `gateway/headers.rs`.
- **Implemented:** line-oriented gateway activity records, rotation, basic file listing/log reads, permissions, bounded structured JSON/CSV export with user/API/endpoint/level/type/date filters, JSON/CSV attachment downloads, and aggregate log statistics (level counts, average response time, and top APIs/users/endpoints). Successful user, API, endpoint, endpoint-validation, and authorization lifecycle; configuration import, rollback, export; security-settings update; generic management create/update/delete; cache clear; and global-IP deny actions now emit structured actor/action/target/status audit records. Configured activity/audit log-write failures now degrade readiness until a subsequent write succeeds. Password-hash failures and revocation-state writes fail closed instead of creating an invalid credential or acknowledging a revocation that was not stored.
- **Gaps:** A payload-free actor/action/route-family/status record now covers every authenticated platform mutation, and authenticated platform responses carry actor/route context into activity logging. `AuditEvent` remains an unused shell outside those helpers. Python's broader textual-log parsing, time-of-day queries, redaction patterns, and in-memory UI log behavior are absent or simplified; unauthenticated sensitive requests still need an explicit no-payload audit policy.
- **Done when:** Port logging permission/redaction/audit/export tests, wire centralized redaction before every sink, record management mutations, and match download content types/filenames/bodies.

### MIG-042 — Configuration export/import/snapshots/rollback

- **Classification/Priority:** Partially migrated / P1.
- **Python source:** `routes/config_routes.py`.
- **Rust source:** platform config functions and `config_snapshots` collection.
- **Implemented:** five configuration domains, domain permissions, single-API export, Python-compatible upsert imports, snapshots captured with the imported state in one memory lock or MongoDB transaction, timestamp-ordered latest rollback, and optional rollback by `snapshot_id`. Imports preserve unrelated records, existing fields and API identifiers, generate missing identifiers, associate endpoints with their API, and skip records missing natural keys. BSON identifiers are preserved through restore. Snapshot-read failures fail closed rather than being reported as an empty snapshot set.
- **Gaps:** Full domain model validation, snapshot consumption behavior, all cache-invalidation side effects, and exact permission codes still need operation-level comparison. The malformed-record test now asserts preserved existing records; its earlier emptied-collection assertion contradicted the pinned Python upsert implementation.
- **Done when:** Port all config tests, support snapshot selection, validate before mutation, define transaction/compensation behavior, and test partial failures in Mongo.

### MIG-043 — Hot-reload configuration

- **Classification/Priority:** Partially migrated / P0.
- **Python source:** `utils/hot_reload_config.py`, hot-reload routes, SIGHUP handler, reload script.
- **Rust source:** `hot_reload.rs`, platform reload routes.
- **Implemented:** JSON/YAML flattening, environment overrides, current/reload endpoints, and effective reload of `GATEWAY_TIMEOUT`, `RETRY_ENABLED`, and `RETRY_MAX_ATTEMPTS` for subsequent REST, GraphQL, and SOAP requests. Reload rejects an unreadable or invalid configuration file rather than retaining stale values.
- **Remaining divergence:** Circuit-breaker, cache, logging, metrics, feature, connection, rate-limit, and gRPC runtime code remain startup-configured and are returned as restart-required. Unix deployments support both SIGHUP and the authenticated reload endpoint.
- **Done when:** Use an atomically swappable runtime config in every advertised subsystem, add SIGHUP, prove before/after behavior for all 22 keys, or reduce the advertised key set to values that truly reload.

### MIG-044 — Security settings persistence and runtime effects

- **Classification/Priority:** Partially migrated / P0.
- **Python source:** security routes/model and `utils/security_settings_util.py`.
- **Rust source:** platform settings singleton and platform/data-plane IP policy.
- **Implemented:** permissioned GET/PUT, materialized settings defaults, settings persistence, memory mode marker, runtime use of whitelist/blacklist/trust/bypass fields, direct-peer validation against saved `xff_trusted_proxies` IP/CIDR entries, opt-in memory autosave with the Python-compatible 900-second default interval when enabled by environment, and fail-closed behavior when the security-policy settings store is unavailable. The memory autosave worker applies persisted enablement, cadence, and Python-compatible absolute or nested-relative dump paths at startup and immediately after a successful settings update.
- **Settings-file follow-up (2026-09-15):** Python-compatible JSON persistence and file fallback are implemented. Existing memory/snapshot documents and MongoDB take precedence; external mode never imports the file. Writes exclude `_id`, use atomic replacement, and remain best-effort like Python. Tests cover missing/invalid/empty files, defaults, failed writes, denied/invalid updates preserving the file, file-only memory recovery, and immediate encrypted autosave on enablement. The real MongoDB/Redis suite verifies external precedence. Compose persists the mirror under `/app/data`; demo storage remains ephemeral.
- **Scalar-validation follow-up:** Boolean strings/numeric zero and one, ASCII integer strings (including signs, whitespace, and valid digit separators), and fractional-number truncation now follow the pinned Pydantic v1 model. Boolean/integer validation error types, minimum-value context, and field ordering match the tested Python cases. Unit and request-level regressions cover typed persistence, runtime publication, ignored null/unknown fields, and rejected updates leaving stored/runtime settings unchanged.
- **Typed-record follow-up:** Management reads/updates, platform IP filtering, login IP limiting, and gateway policy now select `type: security_settings`, matching Python rather than taking the first collection record. Updates preserve unrelated records and do not replace the collection when the security record lacks `_id`. Memory regressions cover typed records with/without identifiers and inserting a missing security record; MongoDB HTTP/reconnection coverage preserves BSON identifiers and unrelated records. Authentication/proxy and platform allow/deny tests now include unrelated settings records. The new memory-read and gateway-policy regressions reproduced the old failures before the fix.
- **Autosave-lifecycle follow-up:** Environment enablement/interval values accept surrounding whitespace, and positive intervals below 60 seconds survive environment/file loading rather than becoming the 900-second default. The worker independently enforces its 60-second minimum wait; HTTP interval validation still requires at least 60. Process-isolated tests use a controlled Tokio clock and real encrypted files to exercise startup, cadence, path/cadence updates, disabling, write-failure health, scheduled recovery, and worker cancellation. The environment cases were checked against helper functions extracted from the pinned Python source.
- **Dump-path coercion follow-up:** JSON boolean/integer/float inputs now use the pinned Pydantic v1 model's string conversion, including `True`/`False`, integral floats, negative zero, scientific notation, and shortest-decimal ties. Ryū is an explicit dependency on its already locked version; no package versions changed. The retained Python image (Pydantic 1.10.26) matches a deterministic sample of 9,995 finite float values. Unit and authenticated HTTP regressions cover model errors, field ordering, normalized GET/PUT/storage/file/runtime values, and invalid updates preserving the document/file/runtime settings. These are model-derived regressions, not additional pinned test mappings.
- **Unicode integer follow-up:** Settings-model and autosave-environment integer strings now accept Unicode decimal digits, mixed scripts, ASCII signs, and underscores only between digits. Superscripts, circled digits, non-ASCII minus signs, embedded whitespace, and malformed separators are rejected. The shared parser preserves the distinction between Python `int(string)` whitespace and environment helpers' prior `str.strip()` (which also strips ASCII information separators). All 680 decimal digits match the retained Python image's Unicode 15.0.0 table across the full scalar range; this describes the observed oracle, not a Python dependency-lock claim. Unit, authenticated HTTP/storage/file/runtime, and isolated environment regressions pass, including atomic rejection and minimum-interval errors.
- **List-model follow-up:** All three list fields now follow Python's `list[str]` input contract: JSON scalar items use the same string coercion as `dump_path`, string contents are preserved, null/container items produce indexed errors, and whole-field non-list values produce `type_error.list`. Null fields preserve prior values and empty lists clear them. The unapproved input-format restriction is removed to satisfy the user's 1:1 baseline requirement; malformed IP patterns remain nonmatching at runtime. Authenticated HTTP coverage verifies normalized GET/PUT/document/file values, immediate policy effects for trusted/untrusted peers, invalid-only allowlists, and rejected updates preserving the document/file/runtime settings. The shared IP matcher repairs the dotted-mask and signed-prefix defects noted in MIG-025.
- **Integer-limit follow-up:** Security interval string validation now applies Pydantic 1.10.26's fixed 4,300-character guard before trimming/coercion. Decimal parsing separately honors the startup `PYTHONINTMAXSTRDIGITS` setting (default 4,300 digits; zero disables that digit check; valid nonzero settings are 640 through 2,147,483,647). This limit counts leading zeros and Unicode digits but excludes signs/whitespace/separators. Invalid configuration prevents startup, matching CPython's acceptance grammar; the value is captured once per process. The environment autosave parser uses only the digit limit, preserving Python's distinction from model validation. Process-isolated HTTP regressions verify default/640/unlimited/5,000 limits, numeric persistence, runtime publication, atomic rejection, and minimum-value errors. Both Compose files pass the setting through. The retained validator source and direct CPython/Pydantic probes establish these two separate limits.
- **Process-lifecycle follow-up:** Actual gateway subprocess tests cover SIGUSR1 with an updated saved path while autosave is disabled, forced-stop/restart recovery, SIGINT final persistence, SIGTERM draining of an active body-reading mutation, restore before enabled autosave, metrics shutdown persistence, and wrong-key/corrupt snapshot refusal without file replacement. Restart selects the saved file's dump path before restore, then publishes settings from the restored document. SIGUSR1/final shutdown use the published path; shutdown stops snapshot tasks and dumps after Axum drains requests. The pinned Python lifespan uses cached settings paths and runs shutdown persistence after Uvicorn's request drain. Existing Rust fail-closed restore behavior is retained.
- **Gaps:** Complete model coercion and autosave process-lifecycle coverage remain open. Known model boundaries include Python integers beyond Rust's `u64` interval range or serde_json's integer representation. General JSON integer decoding and other models are not covered by the security-interval string checks. Environment lock precedence and runtime autosave-setting publication have request-level tests. Concurrent first creation, duplicate typed settings, cross-process autosave-setting publication, repeated/concurrent signals, signal dump failure/recovery, external-mode signals, SIGHUP, and complete background-task failure/cancellation remain open. Unix process tests do not establish Windows lifecycle behavior. The sampled float comparison does not prove every finite float representation; the complete IP syntax/proxy-chain matrix remains in MIG-025.
- **Done when:** Port model/default/file/task tests and verify every setting has an observable runtime effect or is removed from the API.

### MIG-045 — Vault lifecycle and encryption compatibility

- **Classification/Priority:** Partially migrated / P1.
- **Python source:** vault routes/service/models and vault encryption utility.
- **Rust source:** `storage/vault.rs`, platform vault handlers.
- **Implemented:** per-user CRUD, duplicate protection, encryption requirement, metadata masking, and configured key derivation/encryption. The live pinned Python route/service source and container showed that `ResponseModel` discards VaultService's unsupported `data` argument: successful list/get wires are `{}` despite their OpenAPI examples. Rust now preserves that defect, Python's `+00:00` UTC storage timestamps, Pydantic-v1 scalar string coercion and length failures, VAULT_KEY-first error ordering, and the source's update behavior that retains description for omitted/null values. Native regression covers encrypted storage, no secret leak, literal wire bodies, timestamp spelling, scalar coercion, and invalid containers.
- **Gaps:** Bidirectional ciphertext fixtures, complete Pydantic edge matrices, external storage, and full route/service permission/failure tests remain unproven.
- **Done when:** Add bidirectional Python/Rust ciphertext fixtures and port all vault route/service validation and lifecycle cases.

### MIG-046 — Demo seed and developer tools

- **Classification/Priority:** Partially migrated / P2.
- **Python source:** demo routes/utilities, tools routes, chaos utilities/middleware.
- **Rust source:** platform demo/tools handlers and `middleware/chaos.rs`.
- **Implemented:** manual demo seed endpoint, CORS simulator, gRPC environment report, chaos toggles/stats, latency and injected errors/outage flags.
- **Gaps:** Startup `DEMO_SEED=true` is absent. The seed corpus/counts/proto/logs are not compared. gRPC tools reports reflection availability without implementing a reflection server. Chaos state is process-global and leaks between tests; backend outage flags need real storage-path coverage.
- **Done when:** Port demo/tool/chaos tests, add scoped/resettable chaos state, and either implement or accurately report tool capabilities.

### MIG-047 — Startup, background tasks, graceful shutdown, and filesystem migration

- **Classification/Priority:** Partially migrated / P1.
- **Python source:** `doorman.py` lifespan and startup validation.
- **Rust source:** `main.rs`, `config.rs`, storage connect.
- **Implemented:** startup config validation, external gRPC descriptor backfill, memory restore, metrics restore/autosave, persisted security-settings autosave, SIGUSR1 dump, SIGHUP configuration reload, SIGTERM/Ctrl-C graceful dump, and storage initialization.
- **Process evidence:** `tests/process_lifecycle.rs` exercises the actual Unix gateway binary for saved-path SIGUSR1, forced-stop recovery, SIGINT/SIGTERM shutdown, an active mutation completed during draining, restore before autosave, shutdown metrics, and unreadable snapshot refusal. Snapshot worker handles are stopped before the post-drain final dump.
- **Gaps:** Startup demo seed, generated-directory migration, and later-line realtime listener/startup DB checks remain absent. SIGHUP, repeated/concurrent signals, signal dump failure/recovery, external-mode signals, Windows behavior, and complete background-task failure/cancellation still need coverage.
- **Done when:** Make an explicit lifecycle parity table and port each required task/signal/failure/shutdown behavior with process-level tests.

### MIG-048 — Error-code, malformed-input, and response-envelope parity

- **Classification/Priority:** Partially migrated / P0.
- **Python source:** `utils/error_codes.py`, error/response utilities, route exception handling.
- **Rust source:** `PolicyFailure`, `PolicyErrorBody`, platform response helpers, catch-panic layer.
- **Current targeted parity:** Malformed JSON now returns the Python envelope before authentication for typed entity, subscription, credit, vault, tier, security-settings, config-import, memory dump/restore, and tools CORS/chaos mutations. Login and public registration instead return the Python `400 AUTH004` envelope. These paths are native regression-tested against fresh Python-oracle samples.
- **Gap:** Rust still uses several envelope families and generic codes. Generic entity errors lose domain-specific messages. Upstream, storage, validation, auth, and method-not-allowed mappings have not been exhaustively compared.
- **Done when:** Generate an error registry from the Python baseline, map every reachable code/status/body/header to Rust, and add negative tests for all 178 operations plus each gateway policy stage.

### MIG-049 — Structural shell modules and misplaced implementations

- **Classification/Priority:** Partially migrated / P3.
- **Rust shells:** `protocol/graphql.rs`, `protocol/rest.rs`, and `validation/protobuf.rs` are one-line comments. `gateway/retries.rs`, `gateway/context.rs`, `gateway/response.rs`, `middleware/logging.rs`, `middleware/metrics.rs`, and `observability/audit.rs` define unused types. `gateway/headers.rs::is_sensitive` is unused.
- **Nuance:** REST/GraphQL/retry/logging/metrics behavior exists elsewhere, especially in `routes/rest.rs` and `middleware/activity.rs`; empty named modules do not by themselves mean the feature is missing.
- **Remaining work:** Move behavior behind the intended boundaries only after tests protect it. Remove misleading dead types or wire them in. Implement protobuf validation if it is a required contract.
- **Done when:** Module names accurately describe ownership, dead-code searches are clean, and refactoring does not change frozen/differential behavior.

## 6. Baseline behavior not migrated

### MIG-050 — WebSocket rejection/enablement contract

- **Classification/Priority:** Not migrated / P1.
- **Python source:** `middleware/websocket_reject_middleware.py`, mounted with `WEBSOCKETS_ENABLED`.
- **Rust gap:** No WebSocket handshake/close path exists. A request upgrade header is merely treated as hop-by-hop HTTP data. Python closes disabled WebSocket connections with policy code 1008; Rust does not reproduce that protocol behavior.
- **Done when:** Add a WebSocket integration test against Python and Rust for enabled/disabled settings, handshake status, close code/reason, auth/policy, and unsupported paths.

### MIG-051 — SIGHUP hot reload

- **Classification/Priority:** Partially migrated / P0.
- **Python source:** SIGHUP handler in `doorman.py` and reload script.
- **Implemented:** Unix startup registers SIGHUP and invokes the same fail-closed reload path as the authenticated reload endpoint. The currently effective runtime set is `GATEWAY_TIMEOUT`, `RETRY_ENABLED`, and `RETRY_MAX_ATTEMPTS`; invalid reload input retains the prior configuration.
- **Gaps:** The handler lacks process-level coverage, and the remaining advertised settings are intentionally restart-required rather than dynamically applied. Coordinate with MIG-043 before expanding the runtime-swappable set.
- **Done when:** SIGHUP reloads every advertised runtime-configurable value safely and has a process-level test, or the API advertises only the values that truly reload.

### MIG-052 — Legacy generated-directory migration

- **Classification/Priority:** Not migrated / P2.
- **Python source:** `_migrate_generated_directory()` in `doorman.py` moves legacy root `generated/` data into the backend service directory.
- **Rust gap:** No startup compatibility migration exists for previously deployed proto/snapshot/security files.
- **Done when:** Decide the v2 canonical paths, add a safe idempotent migration with collision/traversal tests, and document rollback/recovery.

### MIG-053 — Automatic startup gRPC descriptor backfill

- **Classification/Priority:** Implemented / P1.
- **Python source:** pinned lifespan invokes `backfill_descriptor_sets()` in external mode.
- **Resolution:** External-storage startup now invokes the same reusable descriptor backfill used by `POST /platform/proto/descriptors/backfill`. It scans active gRPC APIs with source, preserves nonempty descriptor sets, records compile/update failures, and logs scanned/updated/skipped/missing counts. Readiness remains fail-closed for any active gRPC API whose descriptor is still unavailable.
- **Verification:** Add/retain external startup coverage with an active gRPC API that has source but no descriptor; startup must populate the descriptor before readiness is evaluated. A compile or storage failure must be visible in startup logs and continue to yield a degraded readiness result.

### MIG-054 — Expired revocation purge

- **Classification/Priority:** Implemented / P0.
- **Python source:** `automatic_purger()` and `purge_expired_tokens()`.
- **Resolution:** Authorization ignores and deletes expired JTI records on use. Startup now runs a storage-native purge, followed by a configurable five-minute periodic purger (`REVOCATION_PURGE_INTERVAL_SECONDS`); it removes only expired JTI records and preserves non-expiring revoke-all records in memory and MongoDB. A failed purge is logged and marks readiness degraded.
- **Verification:** Add/retain memory and external-storage coverage for expired JTI cleanup, preservation of revoke-all records, and readiness degradation/recovery after a purge failure; coordinate with MIG-013.

### MIG-055 — Startup demo seeding

- **Classification/Priority:** Not migrated / P2.
- **Python source:** lifespan checks `DEMO_SEED` and populates users/APIs/endpoints/groups/protos/logs in memory mode.
- **Rust gap:** Only an authenticated manual seed route exists.
- **Done when:** `DEMO_SEED=true` produces the documented demo environment idempotently at startup, or deployment docs and Compose stop promising it.

### MIG-056 — Python utility behaviors with no effective Rust port

- **Classification/Priority:** Not migrated or intentionally omitted / P2 decision.
- **Examples:** `utils/geo_lookup.py` has placeholder geolocation behavior; `utils/email_util.py` is a logging/stub notification path used by tier workflows; Python's standalone generic rate-limit middleware and some gRPC discovery helpers are also explicitly incomplete.
- **Decision needed:** Do not blindly port dead or placeholder code. For each utility, prove whether it is reachable and observable in the pinned server, then either add a contract, record an intentional omission, or implement the advertised feature in both product semantics and tests.

## 7. Later Python `origin/main` features outside the pinned baseline

These items are not failures against commit `10699820`; they are migration-scope risks. They become required if the product target is Python v1.2/latest rather than the frozen parity commit.

### MIG-057 — Decide whether post-baseline Python is in scope

- **Classification/Priority:** Post-baseline not migrated / P0.
- **Evidence:** `git rev-list --left-right --count 10699820...origin/main` reports divergent histories, and the backend diff changes 99 files by about +8,135/-1,653 lines.
- **Done when:** Product ownership chooses the target, creates a new immutable reference if needed, freezes its OpenAPI/tests/contracts, and adds all accepted deltas to this ledger.

### MIG-058 — Transparent host-based routing

- **Classification/Priority:** Post-baseline not migrated / P1 if v1.2 is targeted.
- **Python source:** later `host_gateway_router`, `utils/routing_util.py`, `test_host_routing.py`.
- **Rust gap:** Router fallback returns 404; it does not route arbitrary host/path traffic through a catch-all host policy.
- **Done when:** Port host resolution, conflicts with platform/static paths, trusted host/proxy behavior, and all later-line tests.

### MIG-059 — Native API-builder table/data surface

- **Classification/Priority:** Post-baseline not migrated / P1 if v1.2 is targeted.
- **Python source:** later `routes/api_builder_routes.py` (approximately 1,188 added lines), expanded CRUD service, table/security tests.
- **Rust gap:** Current dashboard “Builder” creates standard API/endpoint documents. Rust has no `/platform/api-builder/*` table/data management surface from the later Python line.
- **Done when:** Freeze the later OpenAPI for the builder, port typed schemas/permissions/dynamic collections, and run its security/table tests against memory and Mongo.

### MIG-060 — Builder triggers, indexes, import/export, and realtime listener

- **Classification/Priority:** Post-baseline not migrated / P1 if v1.2 is targeted.
- **Python source:** later trigger/index/import-export routes, trigger/realtime services, startup listener, integration tests.
- **Rust gap:** No equivalent routes, persistent trigger engine, index management, change listener, or realtime notifications.
- **Done when:** Define delivery/ordering/retry semantics and port the later integration tests with actual external storage where required.

### MIG-061 — Anonymous access, scopes, and API-key expiration

- **Classification/Priority:** Post-baseline not migrated / P0 if v1.2 is targeted.
- **Python source:** later API models, auth/API utilities, `test_anonymous_access.py`, `test_scope_enforcement.py`, `test_api_key_expiry.py`.
- **Rust gap:** Current policy supports public/auth-required flags and credit API keys but not the later anonymous/scope/API-key lifecycle contract.
- **Done when:** Port model fields, token/key validation, precedence, failures, and complete negative matrices without weakening current JWT/subscription policy.

### MIG-062 — OIDC/JWKS authentication

- **Classification/Priority:** Post-baseline not migrated / P0 if v1.2 is targeted.
- **Python source:** later auth/key utilities and `test_oidc_jwks_auth.py`.
- **Rust gap:** JWT verification uses configured local HS/RS keys only; there is no OIDC discovery/JWKS fetch, cache, rotation, issuer mapping, or outage behavior.
- **Done when:** Add SSRF-safe discovery, key caching/rotation, issuer/audience/algorithm enforcement, timeout/failure policy, and all later tests.

### MIG-063 — Pre-authentication gateway-wide IP rate limiting

- **Classification/Priority:** Post-baseline not migrated / P0 if v1.2 is targeted.
- **Python source:** later `middleware/gateway_ip_rate_limit_middleware.py` and tests.
- **Rust gap:** IP policy and authenticated user/tier limits exist, but no independent gateway-wide pre-auth flood limiter with the later environment contract exists.
- **Done when:** Implement before JWT/policy lookup, share counters across nodes, use the trusted-proxy resolver from MIG-025, and match rate headers/tests.

### MIG-064 — Rules engine

- **Classification/Priority:** Post-baseline not migrated / P1 if v1.2 is targeted.
- **Python source:** later `utils/rules_engine.py`, API model fields, and `test_rules_engine.py`.
- **Rust gap:** No corresponding rule parser/evaluator/action integration exists.
- **Done when:** Freeze rule syntax and failure policy, implement deterministic evaluation, validate at API creation, and port tests including unsafe/malformed inputs.

### MIG-065 — Later-line hardening and storage semantics

- **Classification/Priority:** Post-baseline partially/not migrated / P1 if v1.2 is targeted.
- **Examples:** dynamic memory collections, duplicate guards, startup DB validation, tier cache updates, rate-limit headers, user-route/service guards, stronger password/update models, proto changes, and credit/routing fixes.
- **Done when:** Review the 99-file diff commit by commit, convert each observable change into a regression test, and map it to an existing or new `MIG-###` item.

## 8. Verification blockers and test migration work

### MIG-066 — Fix all-target compile failure

- **Classification/Priority:** Verification blocker / P0.
- **Status:** Complete on 2026-08-17 (uncommitted working tree).
- **Resolution:** Parsed the authorization response into `Value` before indexing its `access_token`, with an explicit diagnostic if the response is not valid JSON.
- **Verification:** `cargo test --manifest-path gateway-rs/Cargo.toml --locked --test openapi_parity` passed (1 test); `cargo test --manifest-path gateway-rs/Cargo.toml --locked --no-run` compiled every Rust test target.

### MIG-067 — Restore format and Clippy gates

- **Classification/Priority:** Verification blocker / P0.
- **Status:** Complete on 2026-08-17 (uncommitted working tree).
- **Resolution:** Applied `cargo fmt --all` and replaced the redundant `env::var(...).ok()`/`Some` pattern in discovery host allowlisting with `Ok`.
- **Verification:** `cargo fmt --manifest-path gateway-rs/Cargo.toml --all -- --check` and `cargo clippy --manifest-path gateway-rs/Cargo.toml --locked --all-targets --all-features -- -D warnings` both pass with no warning suppressions.

### MIG-068 — Repair or deliberately revise frozen cache-preflight parity

- **Classification/Priority:** Verification blocker / P0.
- **Status:** Complete on 2026-08-17 (uncommitted working tree).
- **Decision:** Retain Rust’s strict CORS policy. An unallowlisted cache-preflight origin receives `403`/`GTW008`; an explicitly allowed origin receives `204` and CORS headers.
- **Resolution:** Cache preflight now uses the same development default (`http://localhost:3000`) as platform CORS while still requiring an exact allowlist match. The frozen Python response remains in `expected`; `approved_rust_divergence` records the approved Rust response, and the differential scenario reports the unallowlisted-origin difference as approved rather than unexplained.
- **Verification:** `cargo test --manifest-path gateway-rs/Cargo.toml --locked --test runtime` passes (22 tests), `--test parity_contracts` passes (1 test), full `cargo test` passes with the external live-TCP test intentionally ignored; formatting, strict all-target Clippy, and `scripts/check_parity_reference.py` pass.

### MIG-069 — Make auth rate parity test represent the intended proxy model

- **Status:** Complete on 2026-08-17 (uncommitted working tree).
- **Resolution:** Configured `auth_rate_parity` to trust the forwarded address it deliberately injects; the production/default setting remains `false`. Existing client-IP unit coverage verifies that an untrusted forwarded header falls back to the direct peer.
- **Verification:** `cargo test --manifest-path gateway-rs/Cargo.toml --locked --test auth_rate_parity` passes (1 test).

### MIG-070 — Fix live user-onboarding and rate-limit scenarios

- **Status:** Complete on 2026-08-17 (uncommitted working tree).
- **Resolution:** Ported the pinned Python rules: user creation and updates allow an unseeded non-admin role such as `developer`; only assignment or creation of `admin` requires an administrator. Bootstrap `admin` accepts only the Python operational limit fields. A self-update without `manage_users` still cannot change `role`, `groups`, `active`, or `username`.
- **Verification:** `cargo test --manifest-path gateway-rs/Cargo.toml --locked --test live_tests_parity` passes (7 tests); `cargo test --manifest-path gateway-rs/Cargo.toml --locked --lib` passes (82 tests); formatting and strict all-target Clippy pass.

### MIG-071 — Isolate global chaos/test state

- **Status:** Complete on 2026-08-17 (uncommitted working tree).
- **Resolution:** Added a suite-level async mutex and RAII reset guard around the chaos case. The guard resets every chaos atomic before and after the test. The required global-state audit found `GatewayRuntime` counters and circuits are per-`AppState`, storage counters are per storage instance, the gRPC retry counter is local to one test, and the OpenAPI/header statics are immutable. `GLOBAL_ANALYTICS` remains intentionally process-global for production persistence; test-mode request tracking is disabled and its explicit test uses a unique metric key.
- **Verification:** `cargo test --manifest-path gateway-rs/Cargo.toml --locked --test python_parity_suite -- --test-threads=1` and the same target with `--test-threads=4` both pass (4 tests).

### MIG-072 — Expand the Python-to-Rust test migration matrix

- **Classification/Priority:** Verification blocker / P0.
- **Status:** In progress; inventory and CI freshness gate completed on 2026-08-18.
- **Current scale:** 600 pinned Python test functions versus 210 declared Rust tests; 178 documented operations versus 8 frozen contracts and 8 differential scenarios.
- **Delivered (through 2026-09-01):** `parity/test_coverage_ledger.json` now generates one deterministic row for all 600 pinned Python tests from the commit in `parity/reference.json`. It has 96 assertion-level Rust mappings marked `covered`, 1 explicit `approved_changed` security divergence, and 503 explicitly `missing`; no coverage is inferred from a similarly named or broader Rust test. Rust now covers onboarding password update and `/me`, credit-definition lookup, an actual local-upstream REST flow, subscription lifecycle, endpoint CRUD, group-key injection with credit deduction, per-user key override, the exact 200/429/200 rate-limit reset sequence, deterministic in-memory rate-counter expiry/restart, throttle queue rejection, fractional throttle waits, strict tier rate limits (including tier priority over a 1,000,000-request user setting and the three-request/two-RPM batch), public bulk REST and SOAP gateway flows without a client token or subscription, authenticated subscribed SOAP forwarding with XML and SOAPAction, allowed SOAP CORS preflight, the permitted gateway error status/code for a missing endpoint, authenticated GraphQL forwarding to a real local upstream with exact response assertions, operation-scoped GraphQL variable validation for rejected and accepted values, all pinned unit/live IP-policy cases, all pinned bandwidth enforcement/accounting/status/monitor/reset cases, the full pinned platform/data-plane CORS domain, and the full pinned health/monitor domain including aggregate metrics and CSV reporting. All 16 pinned unit/live authorization cases now have assertion-level Rust coverage, including login/status, invalid credentials, refresh/invalidate, CSRF modes, admin token controls, JWT configuration presence, public APIs, and non-public APIs with optional authentication. The user lifecycle unit domain and pinned role/group cases are now fully mapped, and six security settings/tools/logging permission flows are covered. The credentialed-wildcard live case is explicitly approved as changed because Rust rejects the unsafe API configuration with 422 rather than creating it. `parity/test_coverage_overrides.json` records reviewed mappings, `parity/test_coverage_ledger.schema.json` documents the format, and `make parity-ledger`/Rust CI reject a stale ledger while reporting status counts by suite/domain.
- **Remaining work:** Every pinned test now has a reviewed disposition. Add the operation-level positive/auth/validation/not-found/method/storage matrix and convert the reviewed divergence/obsolete dispositions into explicit release decisions where appropriate; the current ledger is test-case coverage, not evidence that every operation mode is covered.
- **Latest coverage update (2026-09-01):** The ledger has 137 assertion-level Rust mappings marked `covered`, 1 `approved_changed` divergence, 4 `approved_obsolete` unmounted diagnostic routes, and 458 `missing` rows. The latest increment completes the configuration and credit domains: scoped export/import permissions, malformed-entry filtering, export auditing, secret-safe credit definitions, and rotation-aware key resolution. It also includes the active-API, API/endpoint CRUD, API CORS, and local-upstream PATCH evidence described above.
- **Current checkpoint (2026-09-19):** The generated ledger now disposes of all 600 pinned Python tests: 533 have assertion-level Rust mappings marked `covered`, 22 are reviewed `approved_changed` behaviors, and 45 are reviewed `approved_obsolete` cases. This is 88.8% direct test coverage, not an 88.8% product-parity claim: the operation-level matrix and end-to-end storage/differential evidence below still govern a 1:1 completion claim.
- **Done when:** Every pinned test has a disposition, every operation has positive/auth/validation/not-found/method/storage cases, and CI reports coverage by operation/domain rather than only a test count.

### MIG-073 — Add external, TCP, differential, performance, and rollback gates

- **Classification/Priority:** Verification blocker / P0 for release.
- **Gaps:** The sole TCP test is ignored by default. Mongo/Redis are not used by integration tests. Differential parity needs separately managed servers and has no checked-in report. Original throughput/p95/p99 and rollback criteria have no evidence. A Rust-only runtime no longer has the original Python rollback path.
- **Done when:** CI starts pinned Python, Rust, upstreams, Mongo, and Redis; runs the full differential/state-transition matrix; runs real TCP/protocol tests; records performance results; and documents/tests the actual rollback strategy for the chosen architecture.

### MIG-074 — Keep the management documentation surface private by default

- **Classification/Priority:** Approved security divergence / P0.
- **Python source:** FastAPI exposes `/platform/openapi.json`, `/platform/docs`, and `/platform/redoc` without authentication.
- **Rust source:** `platform.rs` requires an authenticated principal with `manage_apis` for the same documentation surface.
- **Decision:** Retain Rust's private-by-default behavior. The endpoints enumerate the management API and its request schemas; anonymous publication is unnecessary for a deployed gateway and expands reconnaissance exposure. Operators that need documentation authenticate through the normal administrative flow.
- **Verification:** `platform_documentation_and_registration_are_private_by_default` verifies unauthenticated requests return 401 and an authenticated administrator receives 200. The differential manifest records the unauthenticated OpenAPI result as an approved divergence; `/docs` and `/redoc` share the same authorization path.

## 9. Frozen OpenAPI surface map

This table is a navigation aid, not a parity claim. “Implemented” means a Rust branch exists. The cited migration item describes why the domain is still partial.

| # | Frozen tag/domain | Operations | Rust location | Audit status |
|---:|---|---:|---|---|
| 1 | API | 6 | `platform.rs::api_routes` | Partial: MIG-011, MIG-017 |
| 2 | Analytics | 7 | platform analytics helpers | Partial: MIG-039 |
| 3 | Authorization | 10 | login/authorize/authorization handlers | Partial: MIG-012, MIG-013 |
| 4 | Config | 8 | config export/import/rollback | Partial: MIG-042 |
| 5 | Config Hot Reload | 3 | `hot_reload.rs`, platform routes | Partial: MIG-043, MIG-051 |
| 6 | Credit | 9 | `credit_routes`, credit policy/storage | Partial: MIG-020 |
| 7 | Dashboard | 1 | `dashboard` | Partial: MIG-040 |
| 8 | Demo | 1 | `demo_seed` | Partial: MIG-046; startup gap MIG-055 |
| 9 | Endpoint | 13 | `endpoint_routes`, validation modules | Partial: MIG-018 |
| 10 | Gateway | 13 | operations and protocol routes | Partial: MIG-026–MIG-032 |
| 11 | GraphQL discovery | 3 | `api_discovery_routes` | Partial: MIG-037 |
| 12 | Group | 5 | generic entity handler | Partial: MIG-011, MIG-015 |
| 13 | Logging | 4 | `logging_routes`, activity middleware | Partial: MIG-041 |
| 14 | Memory | 2 | snapshot routes | Strong slice: MIG-002 |
| 15 | Monitor | 3 | liveness/readiness/metrics | Partial: MIG-040 |
| 16 | OpenAPI discovery | 4 | discovery parse/fetch/import | Partial: MIG-035 |
| 17 | Proto | 5 | `proto_routes` | Partial: MIG-038 |
| 18 | Quota | 6 | `quota_routes` | Partial/critical: MIG-022 |
| 19 | Rate Limits | 14 | generic entity plus management routes | Partial: MIG-023 |
| 20 | Role | 6 | generic entity handler | Partial: MIG-011, MIG-015 |
| 21 | Routing | 5 | generic entity plus routing policy | Partial: MIG-016 |
| 22 | Security | 3 | settings/restart handlers | Partial: MIG-044 |
| 23 | Subscription | 5 | subscription handler/policy | Partial: MIG-019 |
| 24 | Tiers | 18 | generic entity plus tier actions/policy | Partial/critical: MIG-021 |
| 25 | Tools | 4 | tools/chaos handlers | Partial: MIG-046 |
| 26 | User | 9 | user handlers | Partial/critical: MIG-014 |
| 27 | Vault | 5 | vault handlers/encryption | Partial: MIG-045 |
| 28 | WSDL discovery | 4 | discovery parse/fetch/import | Partial: MIG-036 |
| 29 | gRPC discovery/Web | 2 | descriptor listing and gRPC-Web route | Partial: MIG-029, MIG-030, MIG-038 |

## 10. Python source-to-Rust ownership map

### 10.1 Middleware

| # | Python module | Rust equivalent | Status |
|---:|---|---|---|
| 1 | `analytics_middleware.py` | `middleware/activity.rs`, analytics aggregator | Partial: local queries/shared writes split (MIG-039) |
| 2 | `latency_injection_middleware.py` | `middleware/chaos.rs` | Implemented, test isolation incomplete (MIG-046, MIG-071) |
| 3 | `logging_middleware.py` | activity/logging modules | Partial (MIG-041) |
| 4 | `rate_limit_middleware.py` | policy rate/quota modules | Partial; managed rules/quota not wired (MIG-022, MIG-023) |
| 5 | `security_audit_middleware.py` | unused `observability/audit.rs` plus activity logs | Not equivalent (MIG-041) |
| 6 | `tier_rate_limit_middleware.py` | `policy/tier.rs` | Implemented but not fully verified (MIG-024) |
| 7 | `websocket_reject_middleware.py` | none | Missing (MIG-050) |

### 10.2 Python services

| # | Python service | Rust ownership | Status |
|---:|---|---|---|
| 1 | `api_service.py` | platform API handler/storage | Partial: MIG-017 |
| 2 | `credit_service.py` | platform credit handler/policy/storage | Partial: MIG-020 |
| 3 | `crud_service.py` | `protocol/crud.rs`, REST CRUD branch | Partial: MIG-031 |
| 4 | `endpoint_service.py` | platform endpoint handler/validation | Partial: MIG-018 |
| 5 | `gateway_service.py` | policy, gateway, protocol, and route modules | Broadly implemented, incompletely proven: MIG-024–MIG-031 |
| 6 | `group_service.py` | generic entity handler and group policy | Partial: MIG-015 |
| 7 | `logging_service.py` | activity logger and platform log routes | Partial: MIG-041 |
| 8 | `rate_limit_rule_service.py` | platform rate-limit management | Partial: MIG-023 |
| 9 | `role_service.py` | generic entity handler and role policy | Partial: MIG-015 |
| 10 | `routing_service.py` | generic entity handler and gateway routing | Partial: MIG-016 |
| 11 | `subscription_service.py` | subscription handler/policy | Partial: MIG-019 |
| 12 | `tier_service.py` | tier handler/policy | Partial: MIG-021 |
| 13 | `user_service.py` | user/auth handlers | Partial: MIG-014 |
| 14 | `vault_service.py` | vault handler/encryption | Partial: MIG-045 |

### 10.3 Utility groups

| # | Python utility group | Rust ownership | Status |
|---:|---|---|---|
| 1 | API resolution/routing/transforms | `gateway/resolution.rs`, `routing.rs`, `transforms.rs` | Strong focused slices: MIG-006; full flow partial |
| 2 | Auth/key/blacklist/password/IP limiter | auth policy, platform auth, config, client IP | Partial: MIG-012, MIG-013, MIG-025 |
| 3 | Cache/database/Redis/async wrappers | storage modules/runtime | Partial: MIG-033, MIG-034 |
| 4 | Limits/throttle/bandwidth/credits | policy modules and shared storage | Partial: MIG-020, MIG-022–MIG-024 |
| 5 | Analytics/metrics/Prometheus/geolocation | observability and activity modules | Partial: MIG-039, MIG-040, MIG-056 |
| 6 | Error/response/correlation/sanitize/audit | response compatibility, request ID, logging shells | Partial: MIG-004, MIG-041, MIG-048 |
| 7 | GraphQL/gRPC/WSDL/validation | protocol/discovery/validation modules | Partial: MIG-027–MIG-030, MIG-035–MIG-038 |
| 8 | Memory/security/demo/email | snapshot, platform settings/demo; no email equivalent | Mixed: MIG-002, MIG-044, MIG-046, MIG-056 |
| 9 | Hot reload | `hot_reload.rs` | Partial: SIGHUP and authenticated reload apply timeout/retry settings; remaining settings are restart-required (MIG-043, MIG-051). |

## 11. Recommended incremental execution order

1. **Stabilize the truth source:** MIG-008, MIG-057, MIG-066, MIG-067.
2. **Make parity executable:** MIG-009, MIG-068–MIG-073. Start with a machine-readable 178-operation ledger.
3. **Close security and identity gaps:** MIG-012–MIG-015, MIG-025, MIG-041, MIG-044, MIG-048, MIG-050, MIG-054.
4. **Close stateful policy gaps:** MIG-019–MIG-024, then validate through real Redis/Mongo under MIG-033/MIG-034.
5. **Complete control-plane contracts:** MIG-011, MIG-016–MIG-018, MIG-035–MIG-045.
6. **Expand protocol parity:** MIG-026–MIG-031, one protocol family at a time with real upstreams.
7. **Complete lifecycle/operations:** MIG-043, MIG-046, MIG-047, MIG-051–MIG-055.
8. **Resolve v1.2 scope:** If selected, execute MIG-058–MIG-065 after freezing a new reference.
9. **Refactor only after green behavior gates:** MIG-010 and MIG-049.

## 12. Rules for future models working this ledger

1. Work one `MIG-###` item or a tightly coupled dependency set at a time.
2. Read the exact pinned Python file with `git show 10699820:<path>` or extract that commit. Do not compare against the local `main` pointer or `origin/main` without explicitly working a post-baseline item.
3. Add or strengthen the Python/frozen/differential contract before changing Rust when the current behavior is ambiguous.
4. Compare five dimensions: response, outgoing upstream request, persistent state, cache/counter state, and logs/metrics/audit side effects.
5. Test memory and external MongoDB/Redis modes for every stateful behavior.
6. Preserve security improvements through documented, versioned divergences rather than quietly calling them parity. Registration visibility, docs visibility, CORS, trusted forwarding, and localhost bypass all need explicit decisions.
7. Never use the embedded OpenAPI document as evidence that a handler works.
8. Never mark a whole domain 1:1 because one happy-path Rust test passes.
9. Update this file with the commit, tests added, commands run, and any approved divergence when completing an item.
10. Preserve unrelated worktree changes. At audit time `.env.example` was already modified and was intentionally left untouched.

## 13. Completion template for each item

When closing an item, append a short completion block under it:

```text
Completed: YYYY-MM-DD, commit <sha>
Python oracle: <commit:path and test names>
Rust implementation: <paths>
Tests added/updated: <paths and cases>
Memory result: <command/result>
External result: <command/result>
Differential result: <report path/result>
Approved divergences: <none or decision link>
```

The migration is complete only when all required baseline items are either verified 1:1 or carry an explicit approved divergence, all P0/P1 verification gates pass, every pinned Python test has a disposition, and the selected product baseline is unambiguous.
