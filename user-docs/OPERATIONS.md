Doorman Operations Runbooks
===========================

Overview
--------
Operational playbooks for common gateway actions with exact commands and example responses. Unless noted, endpoints require an authenticated admin session (manage_gateway or manage_auth permissions as applicable).

Authentication (Admin Session)
------------------------------
- Set a base URL and use a cookie jar for convenience:
  - `export BASE=http://localhost:3001`
  - `export COOKIE=/tmp/doorman.ops.cookies`
- Obtain a JWT session cookie via platform login:
  - Command:
    - curl -i -c "$COOKIE" -X POST \
      -H 'Content-Type: application/json' \
      -d '{"email":"admin@doorman.dev","password":"<ADMIN_PASSWORD>"}' \
      "$BASE/platform/authorization"
  - Look for a `Set-Cookie: access_token_cookie=...;` header. Use this cookie in subsequent commands.

Cache Flush
-----------
- Purpose: Clear all in-memory/redis caches (users, roles, APIs, routing, etc.) and reset rate/throttle counters.
- Endpoint: DELETE `$BASE/api/caches`
- Requirements: Admin user with `manage_gateway` access; authenticated session.
- Command:
  - curl -i -b "$COOKIE" -X DELETE \
    -H 'Content-Type: application/json' \
    "$BASE/api/caches"
- Expected response:
  - Status: 200 OK
  - Body: {"message":"All caches cleared"}

Revoke-All Tokens (Per User)
----------------------------
- Purpose: Immediately revoke all active tokens for a specific user across workers/nodes (uses durable storage when configured).
- Endpoints:
  - Revoke: POST `$BASE/platform/authorization/admin/revoke/{username}`
  - Unrevoke: POST `$BASE/platform/authorization/admin/unrevoke/{username}`
- Requirements: Admin with `manage_auth` access; authenticated session.
- Revoke command:
  - curl -i -b "$COOKIE" -X POST \
    -H 'Content-Type: application/json' \
    "$BASE/platform/authorization/admin/revoke/alice"
- Expected revoke response:
  - Status: 200 OK
  - Body: {"message":"All tokens revoked for alice"}
- Unrevoke command:
  - curl -i -b "$COOKIE" -X POST \
    -H 'Content-Type: application/json' \
    "$BASE/platform/authorization/admin/unrevoke/alice"
- Expected unrevoke response:
  - Status: 200 OK
  - Body: {"message":"Token revocation cleared for alice"}

Configuration reload and restart
--------------------------------
- Purpose: Apply supported HTTP gateway settings and inspect restart requirements.
- `GATEWAY_TIMEOUT`, `RETRY_ENABLED`, and `RETRY_MAX_ATTEMPTS` apply
  to subsequent REST, GraphQL, and SOAP requests; send `SIGHUP` or call the
  authenticated endpoint to reload. Use a rolling deployment or controlled
  restart for all other settings.
- HTTP-triggered reload:
  - Endpoint: POST `$BASE/platform/config/reload`
  - Command:
    - curl -i -b "$COOKIE" -X POST \
      -H 'Content-Type: application/json' \
      "$BASE/platform/config/reload"
  - Expected response:
    - Status: 200 OK
    - Headers: may include `X-Request-ID`
    - Body contains the merged configuration, the three supported values in
      `applied`, and `"restart_required": true` for all other settings.
- Inspect current config and reload hints:
  - Endpoint: GET `$BASE/platform/config/current`
  - Command:
    - curl -i -b "$COOKIE" \
      "$BASE/platform/config/current"
  - Expected response:
    - Status: 200 OK
    - Body includes `data.config` and `restart_required: true`.

Notes
-----
- Request IDs: Many admin endpoints include an `X-Request-ID` response header for traceability; some utility endpoints (e.g., cache flush) may omit it.
- Permissions: Cache flush requires `manage_gateway`. Revoke endpoints require `manage_auth`. Config routes require `manage_gateway`.
- Cookies: Browser and curl examples rely on `access_token_cookie`; alternatively, platform APIs may return an `access_token` field usable in Authorization headers where supported.

Release Candidate Runbook
-------------------------
- V2 launch assumption: fresh deployment, with no existing v1 users. Every user
  must log in to v2. Python-issued sessions are not supported; do not disable
  issuer/audience validation or enable a legacy-token bypass. A live Python
  deployment is not required to launch. The Python-to-Rust steps below are
  compatibility rehearsals using synthetic fixtures, not production migration
  prerequisites. V2 backup, restore, and deployment recovery still require proof.
- Scope: Run this against the exact immutable image digest proposed for release,
  a production-like MongoDB replica set, and a separate Redis instance. Keep
  the generated artifacts under `release-evidence/` and do not overwrite a
  prior candidate's directory.
- Image smoke:
  - Start the candidate with the production environment, then run:
    - `BASE_URL=https://candidate.example.com DOORMAN_ADMIN_EMAIL=<admin> DOORMAN_ADMIN_PASSWORD=<password> bash scripts/smoke.sh`
  - Record the image digest, UTC timestamp, target URL, and a successful result
    in `release-evidence/operations.json` under `image_smoke`.
- Restore rehearsal:
  - Restore a scrubbed MongoDB backup into an isolated candidate database and
    restore the matching Redis snapshot/keyspace. Start a fresh candidate,
    run the smoke command above, and verify a known API, endpoint, role, and
    subscription are present.
  - For memory-mode recovery exercises, mount the candidate data directory
    and set `MEM_DUMP_PATH` inside that mount (for example,
    `/app/data/memory_dump.bin`). Dumps are timestamped as
    `memory_dump-<UTC>.bin`; startup selects the newest matching stem by
    modification time, with Python-compatible default-stem/default-directory
    fallback, and fails closed if the selected file is corrupt. HTTP restore
    reads only the exact requested file; pass the filename returned by dump.
    A path outside the mounted volume is intentionally
    ephemeral and is not valid restore evidence.
  - Record the backup identifier and successful result under `restore_rehearsal`.
- Complete v2 cutover:
  - In an isolated rehearsal, start the pinned Python backend and record
    authentication, management, REST, GraphQL, SOAP, and gRPC behavior using
    representative persisted configuration. Save a recoverable backup.
  - Stop Python, start the Rust candidate against that configuration, and
    log in again before repeating authenticated requests. Verify client-visible responses, identifiers,
    subscriptions, policy counters, and mutation side effects. Record every
    difference and accept only the documented security divergences.
  - Record the Python commit, Rust image digest, backup identity, request
    evidence, and successful result under `cutover`.
- Rollback:
  - Stop the Rust candidate, restore the pre-cutover backup, and restart the
    pinned Python deployment. Verify readiness and the smoke command, then
    prove the restored configuration remains available.
    Do not delete candidate databases or evidence until incident review is
    complete.
  - Record the prior digest, UTC timestamp, smoke result, and successful
    result under `rollback`.
- Final evidence:
  - Write a schema-version-1 `release-evidence/operations.json` such as:
    - `{"schema_version":1,"image_smoke":{"passed":true},"restore_rehearsal":{"passed":true},"cutover":{"passed":true},"rollback":{"passed":true}}`
  - Run `make release-check` with all report variables from `user-docs/TESTS.md`.
    It fails closed if any operational rehearsal is absent, failed, or stale.
