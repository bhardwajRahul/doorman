# Frontend-to-Backend Integration Audit & Endpoint Review

**Date**: 2026-09-14  
**Audited Components**:
- **Backend**: Doorman Rust Gateway (`gateway-rs`) running on port 3001
- **Frontend**: Doorman Next.js 14 Web Client (`web-client`) running on port 3000

---

## 1. Executive Summary

A comprehensive architectural and functional review was performed across all backend gateway endpoints and all frontend UI routes and components. 

The review confirmed that:
1. **Core Gateway Data Plane** (`/api/rest/*`, `/api/graphql/*`, `/api/soap/*`, `/api/grpc/*`, `/grpc-web/*`, `/api/health`, `/api/status`, `/metrics`) is operational in Rust with high-performance routing.
2. **Core Control Plane Entities** (`/platform/api/*`, `/platform/user/*`, `/platform/group/*`, `/platform/role/*`, `/platform/routing/*`, `/platform/tiers/*`, `/platform/security/*`, `/platform/config/*`, `/platform/logging/*`) are mapped and functional for standard CRUD and export flows.
3. **12 Critical Discrepancies and Bugs** were identified between the frontend client implementation and the backend endpoints, including:
   - **2 Runtime Crashes** (`TypeError`) on the `/tiers/[id]/users` and `/quota` pages.
   - **2 Complete UI Rendering Failures** on the `/apis/[apiId]/endpoints` and `/users/[username]` pages when accessed directly or refreshed.
   - **1 Complete Surface Absence** for the API Builder (`/api-builder` and `/api-builder/tables`), which call non-existent `/platform/api-builder/*` routes.
   - **1 Silent Data Misattribution Bug** in `/credits` where assigning credits writes to user `"user"` instead of the selected account.
   - **1 Security Revocation Deadlock** in `/auth-admin` causing permanent admin lockout upon token revocation.
   - **2 Documentation Viewer Failures** in `/documentation` and `/documentation/reference` caused by missing fetch credentials and contradictory iframe security headers (`X-Frame-Options: DENY`, `frame-ancestors 'none'`).

---

## 2. Backend Endpoints Review (What They Do)

The Doorman backend is organized into two primary route trees: **Gateway Traffic Data Plane** (`/api/*`, `/grpc-web/*`, `/metrics`) and **Platform Management Control Plane** (`/platform/*`).

### 2.1. Gateway Traffic Data Plane

| Path Pattern | HTTP Methods | Description & Behavior |
| :--- | :--- | :--- |
| `/api/rest/{api_name}/{api_version}/{*path}` | `ALL` | Proxies incoming REST traffic to configured upstream servers (`api_servers`, `endpoint_servers`, or routing `client_key`). Evaluates rate limits, quotas, auth, IP whitelists/blacklists, header forwarding, and retry policies. |
| `/api/graphql/{api_name}/{api_version}/{*path}` | `ALL` | Executes GraphQL requests against configured upstream GraphQL endpoints with query validation and policy enforcement. |
| `/api/soap/{api_name}/{api_version}/{*path}` | `ALL` | Proxies SOAP XML traffic with WSDL/schema inspection and XML transformation. |
| `/api/grpc/{api_name}/{api_version}/{*path}` | `ALL` | Proxies gRPC traffic using dynamic Protobuf descriptors and reflection. |
| `/grpc-web/{api_name}/{service}/{method}` | `ALL` | Bridges gRPC-Web client requests into backend gRPC calls. |
| `/api/health` | `GET`, `ALL` | Public wire-contract health probe; returns `{"status": "online"}`. |
| `/api/status` | `GET`, `ALL` | Operational gateway status report; returns status, uptime, storage health (Mongo/Redis/Memory), and memory usage. |
| `/api/caches` | `DELETE` | Flushes all in-memory gateway policy, tier, rate limit, and routing caches. |
| `/metrics` | `GET` | Prometheus exposition endpoint for operational scrapers (restricted by IP whitelist or auth token). |

### 2.2. Platform Management Control Plane (`/platform/*`)

| Subsystem | Endpoint | Methods | Description & Behavior |
| :--- | :--- | :--- | :--- |
| **Auth & Session** | `/platform/authorization` | `POST` | Authenticates email and password, rate-limits attempts by IP and account, sets `access_token_cookie` and `csrf_token` cookies, and returns access token. |
| | `/platform/authorization/register` | `POST` | Self-service registration (controlled by `DOORMAN_ALLOW_PUBLIC_REGISTRATION`). |
| | `/platform/authorization/status` | `GET` | Checks if current session cookie/token is valid; returns user identity and role. |
| | `/platform/authorization/refresh` | `POST` | Issues a refreshed access token cookie before expiration. |
| | `/platform/authorization/invalidate` | `POST` | Invalidates current token via JTI revocation and clears session. |
| | `/platform/authorization/admin/status/{username}` | `GET` | Reports active and revocation status for a given user account (`manage_auth` permission). |
| | `/platform/authorization/admin/{action}/{username}` | `POST` | Actions: `revoke` (revokes all tokens), `unrevoke` (clears revocations), `disable` (deactivates account), `enable` (activates account). |
| **APIs** | `/platform/api/all` | `GET` | Returns paginated list of all APIs wrapped in `{"apis": [...]}`. |
| | `/platform/api` | `POST` | Creates a new API configuration. |
| | `/platform/api/{api_name}/{api_version}` | `GET`, `PUT`, `DELETE` | Retrieves, updates, or deletes an API configuration. |
| | `/platform/proto/{api_name}/{api_version}` | `GET`, `POST`, `DELETE` | Uploads, inspects, or deletes Protobuf descriptor files for gRPC APIs. |
| **Endpoints** | `/platform/endpoint/{api_name}/{api_version}` | `GET` | Returns all endpoints registered under an API version, wrapped in `{"response": [...]}`. |
| | `/platform/endpoint` | `POST` | Registers a new endpoint under an existing API. |
| | `/platform/endpoint/{method}/{api_name}/{api_version}/{uri}` | `GET`, `PUT`, `DELETE` | Inspects, modifies (e.g. servers, client URI), or deletes a specific endpoint definition. |
| | `/platform/endpoint/validation` | `POST` | Registers a request/response validation schema for an endpoint. |
| | `/platform/endpoint/validation/{endpoint_id}` | `GET`, `PUT`, `DELETE` | Manages endpoint JSON Schema validation rules. |
| **Users** | `/platform/user/me` | `GET` | Returns authenticated user document, role, groups, UI access, and rate limits. |
| | `/platform/user/all` | `GET` | Returns paginated list of all users wrapped in `{"response": [...]}`. |
| | `/platform/user/{username}` | `GET`, `PUT`, `DELETE` | Manages user document (`manage_users` permission). |
| | `/platform/user/{username}/update-password` | `PUT` | Updates account password after validating password strength and policies. |
| **Groups & Roles** | `/platform/group/all`, `/platform/group/{name}` | `GET`, `POST`, `PUT`, `DELETE` | Manages user groups and assigned API access permissions. |
| | `/platform/role/all`, `/platform/role/{name}` | `GET`, `POST`, `PUT`, `DELETE` | Manages platform roles and granular permissions (`manage_users`, `manage_apis`, etc.). |
| **Routings** | `/platform/routing/all`, `/platform/routing/{key}` | `GET`, `POST`, `PUT`, `DELETE` | Manages transparent host and client-key upstream route mappings. |
| **Subscriptions**| `/platform/subscription/subscriptions/{username}` | `GET` | Lists APIs to which a user is subscribed. |
| | `/platform/subscription/available-apis/{username}` | `GET` | Lists APIs eligible for user subscription based on group membership. |
| | `/platform/subscription/subscribe` | `POST` | Subscribes a user to an API version. |
| | `/platform/subscription/unsubscribe` | `POST` | Removes user subscription from an API version. |
| **Credits** | `/platform/credit/defs` | `GET` | Lists all credit group definitions. |
| | `/platform/credit/defs/{group}` | `GET` | Inspects a specific credit definition. |
| | `/platform/credit` | `POST` | Creates a new credit definition. |
| | `/platform/credit/{group}` | `PUT`, `DELETE` | Modifies or deletes a credit definition. |
| | `/platform/credit/all` | `GET` | Returns all user credit balances and tokens. |
| | `/platform/credit/{username}` | `GET`, `POST` | Inspects or saves user-specific credit balances, tiers, and API keys. |
| **Tiers** | `/platform/tiers` | `GET`, `POST` | Lists all tiers (`{"response": [...]}`) or creates a new tier. |
| | `/platform/tiers/{tier_id}` | `GET`, `PUT`, `DELETE` | Inspects, modifies, or deletes a specific rate limit/quota tier. |
| | `/platform/tiers/statistics/all` | `GET` | Returns tier assignment counts: `{"assignments": <count>}`. |
| | `/platform/tiers/{tier_id}/users` | `GET` | Returns users assigned to a tier: `{"users": [...], "count": <count>}`. |
| | `/platform/tiers/assignments` | `GET`, `POST` | Lists all user tier assignments or assigns a user to a tier. |
| | `/platform/tiers/assignments/{user_id}` | `DELETE` | Removes a user tier assignment. |
| **Quota** | `/platform/quota/status` | `GET` | Returns user quota status: `{"user_id": username, "quotas": [...]}`. |
| | `/platform/quota/usage/history` | `GET` | Returns quota usage history. |
| | `/platform/quota/burst/status` | `GET` | Returns burst allowance status. |
| **Analytics** | `/platform/dashboard` | `GET` | Returns dashboard statistics: request counts, active users, new APIs, monthly usage. |
| | `/platform/analytics/overview` | `GET` | Returns traffic metrics, percentiles (p50-p99), error rates, bandwidth. |
| | `/platform/analytics/timeseries` | `GET` | Returns time-bucketed timeseries for request volume, errors, and latency. |
| | `/platform/analytics/top-apis`, `/top-users`, `/top-endpoints` | `GET` | Returns sorted rankings of top traffic consumers and routes. |
| **Security & System** | `/platform/security/settings` | `GET`, `PUT` | Configures global IP whitelists/blacklists, proxy trust, and autosave. |
| | `/platform/security/restart` | `POST` | Schedules a graceful gateway restart. |
| | `/platform/memory/dump`, `/platform/memory/restore` | `POST` | Triggers on-demand memory state backup and restoration. |
| **Configuration**| `/platform/config/export/{all\|apis\|roles\|groups\|routings\|endpoints}` | `GET` | Exports system configuration as JSON. |
| | `/platform/config/import` | `POST` | Imports configuration entities with conflict resolution. |
| | `/platform/config/current`, `/config/reloadable-keys`, `/config/reload` | `GET`, `POST` | Inspects live config and triggers hot reload for runtime timeouts/retries. |
| **Logging** | `/platform/logging/logs` | `GET` | Queries paginated gateway request and audit logs with filtering. |
| | `/platform/logging/logs/download` | `GET` | Streams full gateway log dump. |
| **Tools** | `/platform/tools/cors/check` | `POST` | Simulates and evaluates preflight CORS checks against gateway policies. |
| | `/platform/tools/grpc/check` | `GET` | Tests gRPC and protoc tool availability. |
| | `/platform/tools/chaos/stats`, `/chaos/toggle` | `GET`, `POST` | Fault injection controls (Mongo/Redis outage simulation, latency, error status). |
| | `/platform/tools/rate-limit-simulator` | `POST` | Simulates traffic against rate limit rules. |
| **Documentation**| `/platform/openapi.json` | `GET` | Returns the complete OpenAPI 3.1 schema. |
| | `/platform/docs`, `/platform/redoc` | `GET` | Embedded Swagger UI and ReDoc HTML consoles. |
| **Monitor** | `/platform/monitor/liveness`, `/readiness`, `/metrics`, `/report` | `GET` | Health probes, readiness checks, internal metrics, and CSV reports. |

---

## 3. UI Architecture and Endpoint Interaction

The frontend is built using **Next.js 14 (App Router)** in `web-client/src`:

1. **Routing & Guards**:
   - Page routes are defined under `web-client/src/app/*`.
   - Global layout and navigation rail are provided by [`Layout.tsx`](file:///home/mitchell/git/doorman/web-client/src/components/Layout.tsx).
   - Route authorization is enforced by [`ProtectedRoute.tsx`](file:///home/mitchell/git/doorman/web-client/src/components/ProtectedRoute.tsx) and Next.js [`middleware.ts`](file:///home/mitchell/git/doorman/web-client/src/middleware.ts).
2. **Authentication & Session Lifecycle**:
   - Handled by [`AuthContext.tsx`](file:///home/mitchell/git/doorman/web-client/src/contexts/AuthContext.tsx).
   - On load, it checks session validity via `GET /platform/authorization/status`, fetches user details from `GET /platform/user/me`, and resolves role permissions via `GET /platform/role/{role}`.
   - Proactively refreshes the session every 10 minutes via `POST /platform/authorization/refresh`.
   - Cleans up state and calls `POST /platform/authorization/invalidate` on logout.
3. **HTTP Client & Envelope Unwrapping**:
   - Handled by [`utils/http.ts`](file:///home/mitchell/git/doorman/web-client/src/utils/http.ts) and [`utils/api.ts`](file:///home/mitchell/git/doorman/web-client/src/utils/api.ts) (`fetchJson`, `getJson`, `postJson`, `putJson`, `delJson`).
   - Requests include `credentials: 'include'` and attach `X-CSRF-Token` headers from the `csrf_token` cookie.
   - **Crucial Behavior**: `fetchJson` automatically checks if the returned JSON contains a `'response'` key (`'response' in data`). If so, it unwraps `data.response` and returns it directly. If no `'response'` key exists, it returns `data` unchanged.
4. **URL Resolution & Proxying**:
   - Handled by [`utils/config.ts`](file:///home/mitchell/git/doorman/web-client/src/utils/config.ts) (`SERVER_URL`).
   - If `NEXT_PUBLIC_GATEWAY_URL` is empty, requests use same-origin (`window.location.origin`), and Next.js rewrites (`next.config.mjs`) forward `/platform/*` and `/api/*` to the backend. If `NEXT_PUBLIC_GATEWAY_URL` is provided, requests connect directly to the gateway host.

---

## 4. Issues & Failures: Detailed Findings & Remediation

### Issue 1: Endpoints List in API Detail View (`/apis/[apiId]/endpoints`) — Two Fatal Bugs
- **Files**: [`web-client/src/app/apis/[apiId]/endpoints/page.tsx`](file:///home/mitchell/git/doorman/web-client/src/app/apis/[apiId]/endpoints/page.tsx#L181-L235)
- **Impact**: **High / Complete Feature Failure** — Users cannot see or manage endpoints for an API.
- **Bug 1A (Direct Navigation Hang)**: Lines 181–190 initialize `apiName` and `apiVersion` only from `sessionStorage.getItem('selectedApi')`. If a user refreshes the browser, bookmarks the page, or clicks a direct link, `sessionStorage` is empty. The `useEffect` on line 228 only triggers `loadEndpoints()` if `apiName && apiVersion` are truthy. The fallback logic to resolve `apiId` to `apiName` via `/platform/api/all` was placed inside `loadEndpoints()`, which is never invoked. The page hangs in an empty state.
- **Bug 1B (Envelope Unwrapping Mismatch)**: In `loadEndpoints()` (lines 206–211), the backend endpoint `GET /platform/endpoint/{api_name}/{api_version}` returns `{"response": [ {...} ]}`. `fetchJson` unwraps `data.response` into a raw Array. The page code then does:
  ```ts
  const data = await fetchJson(...)
  list = data.endpoints || data.response?.endpoints || []
  ```
  Since `data` is an Array, `data.endpoints` and `data.response` are `undefined`. `list` evaluates to `[]`, and `setEndpoints([])` is called. **Endpoints are never displayed.**
- **Remediation**:
  1. Separate the API lookup into an effect that triggers whenever `apiId` is present, fetching `/platform/api/all` to populate `apiName` and `apiVersion` if not in `sessionStorage`.
  2. Update line 209 to:
     ```ts
     list = Array.isArray(data) ? data : (data.endpoints || data.response?.endpoints || [])
     ```

---

### Issue 2: Logging Page Endpoint Overrides Check (`/logging`) — Silent Array Access Failure
- **File**: [`web-client/src/app/logging/page.tsx`](file:///home/mitchell/git/doorman/web-client/src/app/logging/page.tsx#L156-L165)
- **Impact**: **Medium / Degraded UX** — Log entries fail to indicate when endpoint-level server overrides took effect.
- **Detail**: In `ensureEndpointOverridesLoaded` (lines 157–159):
  ```ts
  const responseData: any = await fetchJson(`${SERVER_URL}/platform/endpoint/${encodeURIComponent(api_name)}/${encodeURIComponent(api_version)}`)
  const data = responseData
  const eps: any[] = data.endpoints || []
  ```
  Because `fetchJson` unwraps the response envelope, `data` is already an Array. `data.endpoints` is `undefined`, so `eps` is set to `[]`. Endpoint server overrides are never mapped.
- **Remediation**: Update line 159 to:
  ```ts
  const eps: any[] = Array.isArray(data) ? data : (data.endpoints || data.response?.endpoints || [])
  ```

---

### Issue 3: Tier Users Page Runtime Crash (`/tiers/[id]/users`) — Uncaught TypeError
- **File**: [`web-client/src/app/tiers/[id]/users/page.tsx`](file:///home/mitchell/git/doorman/web-client/src/app/tiers/[id]/users/page.tsx#L72-L73)
- **Impact**: **Critical / White Screen Crash** — The page crashes immediately on load.
- **Detail**:
  - In `fetchData()` (line 72):
    ```ts
    const assignmentsData = await getJson(`${SERVER_URL}/platform/tiers/${tierId}/users`)
    setAssignments(assignmentsData || [])
    ```
  - The backend returns `{"users": [...], "count": ...}` (there is no `"response"` key, so `getJson` returns the object as-is).
  - `setAssignments` assigns the raw object `{ users: [...], count: ... }` to `assignments`.
  - In the JSX (line 220 and 236):
    `assignments.length` is `undefined`, and `assignments.map(...)` throws:
    `TypeError: assignments.map is not a function`.
- **Remediation**: Update line 73 to:
  ```ts
  setAssignments(Array.isArray(assignmentsData) ? assignmentsData : (assignmentsData?.users || []))
  ```

---

### Issue 4: Tiers Overview Page Stats Empty (`/tiers`) — Object vs Array Mismatch
- **File**: [`web-client/src/app/tiers/page.tsx`](file:///home/mitchell/git/doorman/web-client/src/app/tiers/page.tsx#L101-L103)
- **Impact**: **Medium / Missing Data** — Statistics columns in the tiers table are always empty.
- **Detail**:
  - In `fetchStats()` (line 101):
    ```ts
    const data = await getJson(`${SERVER_URL}/platform/tiers/statistics/all`)
    setStats(Array.isArray(data) ? data : [])
    ```
  - The frontend expects an array of per-tier stats (`[{ tier_id, total_users, ... }]`).
  - The backend returns an aggregate assignment count object: `{"assignments": <number>}`.
  - Because `Array.isArray(data)` is false, `stats` is set to `[]`. `getTierStats(tierId)` on line 143 always returns `undefined`.
- **Remediation**: Either update backend `GET /platform/tiers/statistics/all` to compute and return an array of per-tier assignment stats, or adapt `tiers/page.tsx` to handle the aggregate count or query assignments per tier.

---

### Issue 5: Quota Dashboard Page Runtime Crash (`/quota`) — Uncaught TypeError
- **File**: [`web-client/src/app/quota/page.tsx`](file:///home/mitchell/git/doorman/web-client/src/app/quota/page.tsx#L58-L60)
- **Impact**: **Critical / White Screen Crash** — Accessing `/quota` crashes the application.
- **Detail**:
  - Line 58 fetches `GET /platform/quota/status` and stores the response in `data`.
  - The backend returns only: `{"user_id": username, "quotas": [...]}`.
  - In JSX (lines 133, 149, 169), the component unconditionally dereferences:
    `{data.tier_info.display_name}`
    `{data.tier_info.features.length > 0}`
    `{data.usage_summary.has_exhausted}`
  - Both `data.tier_info` and `data.usage_summary` are `undefined`, throwing:
    `TypeError: Cannot read properties of undefined (reading 'display_name')`.
- **Remediation**:
  1. Use optional chaining (`data?.tier_info?.display_name`, `data?.usage_summary?.has_exhausted`) and provide fallback empty states in `quota/page.tsx`.
  2. Enhance backend `GET /platform/quota/status` to include user tier metadata and summary flags if available.

---

### Issue 6: Credit Assignment & Deletion Broken (`/credits`) — Path Misinterpretation
- **File**: [`web-client/src/app/credits/page.tsx`](file:///home/mitchell/git/doorman/web-client/src/app/credits/page.tsx#L168-L195)
- **Impact**: **High / Data Misattribution & Deletion Failure**
- **Detail**:
  - **Assignment Bug**: Line 168 calls:
    `POST /platform/credit/user` with body `{ username: assignForm.username, ... }`.
    In `gateway-rs/src/routes/platform.rs` (line 5230–5240), the backend parses any `POST /platform/credit/{suffix}` by setting `value["username"] = json!(suffix)`. Because `suffix` is `"user"`, the backend saves credits for an account literally named `"user"`! The intended user never receives credits.
  - **Deletion Bug**: Line 190 calls:
    `DELETE /platform/credit/user/{username}/{creditGroup}`.
    The backend router matches `DELETE /platform/credit/{suffix}` and attempts to delete a credit definition from `credit_defs` where `api_credit_group == suffix`. It attempts to delete a definition named `"user/{username}/{creditGroup}"` and returns `404 Credit definition not found`.
- **Remediation**:
  1. Fix the frontend in `credits/page.tsx` to call the actual user credit endpoints:
     - Assign: `POST /platform/credit/{username}` with body `{ "users_credits": { [credit_group]: { "tier": tier_name, "credits": ... } } }`.
     - Delete/Update: `POST /platform/credit/{username}` with the credit group removed.
  2. Or add explicit `/platform/credit/user` handler routes in `gateway-rs`.

---

### Issue 7: User Detail Page Direct Access / Refresh Failure (`/users/[username]`)
- **File**: [`web-client/src/app/users/[username]/page.tsx`](file:///home/mitchell/git/doorman/web-client/src/app/users/[username]/page.tsx#L122-L191)
- **Impact**: **Medium / Direct Linking Failure** — Refreshing or navigating directly to `/users/{username}` fails.
- **Detail**:
  - Lines 122–191 check `sessionStorage.getItem('selectedUser')`.
  - If a user opens the page directly or refreshes, `sessionStorage` is empty. The code immediately enters the `else` branch (lines 187–190), sets `setError('No user data found')`, and stops loading.
  - It does not attempt to query `GET /platform/user/{username}` (unlike `groups/[groupName]` and `roles/[roleName]`, which properly fetch from the backend on cache miss).
- **Remediation**: In the `else` branch, add a call to `GET /platform/user/${encodeURIComponent(username)}` to populate the user details.

---

### Issue 8: API Builder Surface Completely Unimplemented in Backend (`/api-builder` and `/api-builder/tables`)
- **Files**: [`web-client/src/app/api-builder/page.tsx`](file:///home/mitchell/git/doorman/web-client/src/app/api-builder/page.tsx#L182), [`web-client/src/app/api-builder/tables/page.tsx`](file:///home/mitchell/git/doorman/web-client/src/app/api-builder/tables/page.tsx#L433)
- **Impact**: **High / 404 Route Failure** — The API Builder UI is completely unusable.
- **Detail**:
  - Both pages immediately request `/platform/api-builder/tables`, `/platform/api-builder/tables/{collection}/query`, etc.
  - `gateway-rs` does not implement `/platform/api-builder/*` (noted in `PYTHON_TO_RUST_MIGRATION_AUDIT.md` under `MIG-059`). All requests return `404 Platform route does not exist`.
  - Additionally, APIs built through the builder form have `api_servers: []`, meaning the gateway has no upstream host to proxy to when requests hit `/api/rest/{api_name}/{version}/{resource}`.
- **Remediation**: Implement the native `/platform/api-builder/*` CRUD routes in `gateway-rs`, or disable/hide the "Builder" navigation item until the backend surface is ported.

---

### Issue 9: API Documentation Viewer & Iframe Embedding (`/documentation` and `/documentation/reference`)
- **Files**: [`web-client/src/components/OpenApiViewer.tsx`](file:///home/mitchell/git/doorman/web-client/src/components/OpenApiViewer.tsx#L35), [`web-client/src/app/documentation/reference/page.tsx`](file:///home/mitchell/git/doorman/web-client/src/app/documentation/reference/page.tsx#L50-L55)
- **Impact**: **High / Documentation Failure**
- **Bug 9A (OpenApiViewer 401 Unauthorized)**: Line 35 in `OpenApiViewer.tsx` calls:
  `fetch(openapiUrl, { cache: 'no-store' })` without `credentials: 'include'`.
  `/platform/openapi.json` requires authentication (`manage_apis` permission). Without credentials, the request returns `401 Unauthorized`.
- **Bug 9B (Iframe Security Rejection)**: `documentation/reference/page.tsx` embeds `/platform/redoc` and `/platform/docs` via `<iframe>`. The backend sets:
  ```http
  X-Frame-Options: DENY
  Content-Security-Policy: default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'; img-src 'self' data:; connect-src 'self';
  ```
  Browsers strictly refuse to render the iframes due to `X-Frame-Options: DENY` and `frame-ancestors 'none'`. Furthermore, the Swagger and ReDoc HTML pages reference CDN scripts which violate `default-src 'none'`.
- **Remediation**:
  1. Add `credentials: 'include'` to the fetch call in `OpenApiViewer.tsx`.
  2. For `/platform/docs` and `/platform/redoc`, relax `X-Frame-Options` (or set `SAMEORIGIN`) and update `Content-Security-Policy` to allow `frame-ancestors 'self'` and CDN scripts for Swagger UI/ReDoc.

---

### Issue 10: Token Revocation Deadlock / Permanent Account Lockout (`/auth-admin`)
- **Files**: [`web-client/src/app/auth-admin/page.tsx`](file:///home/mitchell/git/doorman/web-client/src/app/auth-admin/page.tsx#L44), [`gateway-rs/src/routes/platform.rs`](file:///home/mitchell/git/doorman/gateway-rs/src/routes/platform.rs#L3285-L3300)
- **Impact**: **Critical / Security & Availability Vulnerability**
- **Detail**:
  - When an administrator clicks "Revoke Tokens" on an account (or their own account), `POST /platform/authorization/admin/revoke/{username}` creates a `{"type": "revoke_all", "username": username}` entry in the `revocations` storage.
  - The `authorize()` middleware in `platform.rs` checks:
    ```rust
    if matches!(storage.find_one("revocations", &json!({"type": "revoke_all", "username": username})).await, Ok(Some(_))) {
        return Err(error(StatusCode::UNAUTHORIZED, "AUTH003", "Token has been revoked", request_id));
    }
    ```
  - It does **not** compare the token issuance time (`iat`) against the revocation timestamp.
  - When the user logs in again (`POST /platform/authorization`), a new valid token is issued. However, on the very next request, `authorize()` sees the `revoke_all` entry and immediately returns `401 Token has been revoked`.
  - Because the user cannot authorize, they cannot call `POST /platform/authorization/admin/unrevoke/{username}`. The account is permanently locked out unless another administrator clears the revocation or the database is manually edited.
- **Remediation**:
  - Store a timestamp `revoked_at` in the `revoke_all` entry.
  - In `authorize()`, only reject tokens where `claims.iat <= revoked_at`. Tokens issued after `revoked_at` must be accepted.

---

### Issue 11: Dead Code in Auth Utilities (`web-client/src/utils/auth.ts`)
- **File**: [`web-client/src/utils/auth.ts`](file:///home/mitchell/git/doorman/web-client/src/utils/auth.ts#L57-L59)
- **Impact**: **Low / Code Quality**
- **Detail**: `getTokenFromCookie()` unconditionally returns `null`. Helper functions like `isAuthenticated()`, `canAccessUI()`, and `canAccessPage()` in `utils/auth.ts` will always return `false` if imported directly.
- **Remediation**: Update `getTokenFromCookie()` to read `access_token_cookie` using `getCookie('access_token_cookie')`, or remove unused stub exports in favor of `useAuth()`.

---

### Issue 12: Next.js Middleware Cross-Origin Assumption (`web-client/src/middleware.ts`)
- **File**: [`web-client/src/middleware.ts`](file:///home/mitchell/git/doorman/web-client/src/middleware.ts#L58-L65)
- **Impact**: **Medium / Deployment Configuration Dependency**
- **Detail**: `middleware.ts` inspects `req.cookies.get('access_token_cookie')` on the server. If `NEXT_PUBLIC_GATEWAY_URL` is pointed to an external domain where cookies are not shared with the Next.js host, `middleware.ts` redirects to `/login` in a loop.
- **Remediation**: Document that the web client and gateway must either be deployed behind a unified reverse proxy (same-origin), share the root cookie domain (`COOKIE_DOMAIN`), or use the Next.js rewrite proxy.

---

## 5. Verification Matrix Summary

| Area / Page | Endpoint(s) Tested | Method | Backend Status | Frontend Integration Status | Notes |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Login / Logout** | `/platform/authorization`, `/invalidate` | POST | 200 OK | **Working** | Cookie setting, validation, and invalidation work as expected. |
| **Auth Status** | `/platform/authorization/status` | GET | 200 OK | **Working** | Used by `AuthContext` on mount and interval. |
| **Dashboard** | `/platform/dashboard` | GET | 200 OK | **Working** | Schema matches `DashboardData` interface. |
| **Analytics** | `/platform/analytics/overview`, `/timeseries` | GET | 200 OK | **Working** | Ranges `24h`, `7d`, `30d` render correctly. |
| **APIs (List/Add)** | `/platform/api/all`, `/platform/api` | GET, POST | 200 / 201 | **Working** | Pagination, filtering, creation work. |
| **API Detail** | `/platform/api/{name}/{ver}` | GET, PUT, DEL | 200 OK | **Working** | Edit and deletion work. |
| **API Endpoints** | `/platform/endpoint/{name}/{ver}` | GET | 200 OK | **BROKEN (Issue 1)** | Unwrapping bug causes endpoint list to render empty; direct link fails. |
| **Endpoint Add** | `/platform/endpoint` | POST | 201 OK | **Working** | Endpoints are persisted to storage. |
| **Endpoint Edit/Del** | `/platform/endpoint/{m}/{name}/{v}/{uri}` | PUT, DEL | 200 OK | **Working** | Server edits and deletions work. |
| **Validations** | `/platform/endpoint/validation/*` | GET, POST, DEL | 200 / 201 | **Working** | Schema validation CRUD works. |
| **API Builder** | `/platform/api-builder/*` | ANY | 404 Not Found | **BROKEN (Issue 8)** | Missing backend surface (`MIG-059`). |
| **Users (List/Add)**| `/platform/user/all`, `/platform/user` | GET, POST | 200 / 201 | **Working** | User onboarding and pagination work. |
| **User Detail** | `/platform/user/{username}` | GET, PUT, DEL | 200 OK | **BROKEN (Issue 7)** | Direct URL access fails with "No user data found". |
| **Groups** | `/platform/group/all`, `/group/{name}` | ALL | 200 / 201 | **Working** | CRUD and API access binding work. |
| **Roles** | `/platform/role/all`, `/role/{name}` | ALL | 200 / 201 | **Working** | CRUD and permission toggles work. |
| **Subscriptions** | `/platform/subscription/*` | GET, POST | 200 OK | **Working** | Subscribe and unsubscribe work. |
| **Credits (Defs)** | `/platform/credit/defs/*` | ALL | 200 / 201 | **Working** | Definition CRUD works. |
| **Credits (Users)**| `/platform/credit/user/*` | POST, DEL | 200 / 404 | **BROKEN (Issue 6)** | Saves to `"user"` username; deletion 404s. |
| **Tiers (List/Add)**| `/platform/tiers`, `/platform/tiers/{id}` | ALL | 200 / 201 | **Working** | Tier creation, edit, deletion work. |
| **Tiers (Stats)** | `/platform/tiers/statistics/all` | GET | 200 OK | **BROKEN (Issue 4)** | Object vs array mismatch; stats empty. |
| **Tier Users** | `/platform/tiers/{id}/users` | GET | 200 OK | **BROKEN (Issue 3)** | Runtime `TypeError: assignments.map is not a function`. |
| **Quota** | `/platform/quota/status` | GET | 200 OK | **BROKEN (Issue 5)** | Runtime `TypeError: Cannot read properties of undefined`. |
| **Settings** | `/platform/user/me`, `/update-password` | GET, PUT | 200 OK | **Working** | Profile update and password change work. |
| **Security** | `/platform/security/settings`, `/restart` | GET, PUT, POST | 200 OK | **Working** | Settings save and restart scheduling work. |
| **Caches** | `/api/caches` | DELETE | 200 OK | **Working** | Cache flush works when CSRF token provided. |
| **Import / Export**| `/platform/config/export/*`, `/import` | GET, POST | 200 OK | **Working** | Export downloads and imports work. |
| **Logging** | `/platform/logging/logs`, `/download` | GET | 200 OK | **Working / Partial (Issue 2)** | Log queries work; endpoint override detection broken. |
| **Tools** | `/platform/tools/cors/check` | POST | 200 OK | **Working** | Simulated preflight CORS checking works. |
| **Auth Admin** | `/platform/authorization/admin/*` | POST | 200 OK | **BROKEN (Issue 10)** | Token revocation causes permanent admin deadlock. |
| **Documentation** | `/platform/openapi.json`, `/docs` | GET | 200 OK | **BROKEN (Issue 9)** | Missing credentials; iframe headers blocked. |

---

## 6. Recommended Next Steps

1. **Fix High-Impact UI Bugs**:
   - In `web-client/src/app/apis/[apiId]/endpoints/page.tsx`, fix the array unwrapping and direct-link API lookup.
   - In `web-client/src/app/tiers/[id]/users/page.tsx`, unwrap `assignmentsData?.users || []` to fix the crash.
   - In `web-client/src/app/quota/page.tsx`, guard against undefined `tier_info` and `usage_summary`.
   - In `web-client/src/app/users/[username]/page.tsx`, add the backend fetch fallback on direct navigation.
   - In `web-client/src/app/credits/page.tsx`, fix the user credit assignment and deletion URLs.
   - In `web-client/src/components/OpenApiViewer.tsx`, add `credentials: 'include'`.
2. **Fix Backend Security & Routing Issues**:
   - In `gateway-rs/src/routes/platform.rs`, update `authorize()` to respect token issuance time (`iat`) relative to `revoked_at` to resolve the revocation deadlock.
   - Update `security_headers.rs` to allow iframe embedding from same-origin (`X-Frame-Options: SAMEORIGIN` and `frame-ancestors 'self'`) on `/platform/docs` and `/platform/redoc`.
   - Implement or gracefully stub `/platform/api-builder/*` in Rust (`MIG-059`).
