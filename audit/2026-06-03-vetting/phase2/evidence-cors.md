# NovaCRM Phase 2 — Production CORS Audit

**Target:** `https://api-production-c080.up.railway.app` (NovaCRM API, Railway `api` service)
**Date:** 2026-06-03
**Scope:** Read-only live probes + source/config review. No writes, no load.
**Question:** Is a malicious cross-origin reflected back with credentials (CORS misconfig allowing credentialed cross-site reads)?

---

## 1. Source review — `/tmp/crm-signup-fix/apps/api/app/main.py`

CORS middleware (lines 90-97):

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_origin_regex=settings.CORS_ORIGIN_REGEX or None,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

- `allow_credentials=True`.
- `allow_origins=origins` — an **explicit allowlist** built (lines 80-88) from
  `FRONTEND_URL` + comma-split `CORS_ORIGINS` + `http://localhost:3000` + `http://localhost:3001`,
  de-duplicated, empties dropped.
- `allow_origin_regex=settings.CORS_ORIGIN_REGEX or None` — regex path is only active if the
  env var is a non-empty string; otherwise it is `None` (regex matching disabled).

This is Starlette's `fastapi.middleware.cors.CORSMiddleware`. It does **exact** allowlist matching
and, when `allow_credentials=True`, it echoes the request `Origin` into `Access-Control-Allow-Origin`
**only if the origin is allowed** — it never emits `*` with credentials. A non-allowed origin gets
no `Access-Control-Allow-Origin` header at all (and a disallowed *preflight* returns HTTP 400).

## 2. Production config — Railway `api` service

```
$ cd /mnt/external/Projects/crm-agentic && railway variables --service api --json | python3 -c "..."
CORS_ORIGIN_REGEX= ''
FRONTEND_URL=       'https://www.riphere.com'
CORS_ORIGINS=       'https://riphere.com,https://web-production-3d12f.up.railway.app'
```

- **`CORS_ORIGIN_REGEX` is empty** → `settings.CORS_ORIGIN_REGEX or None` evaluates to `None`.
  The wildcard/family regex path is **disabled in production**. Only the exact allowlist applies.
- Effective allowlist:
  `https://www.riphere.com`, `https://riphere.com`,
  `https://web-production-3d12f.up.railway.app`, `http://localhost:3000`, `http://localhost:3001`.

(Note: the real domain is `riphere.com`, not `riphere.com` as the task prompt assumed. Probes below
cover both the literal task-prompt origin and near-matches against the actual `riphere.com` domain.)

## 3. Live probes

### PROBE 1 — fully malicious origin `https://evil.example.com`
Preflight (OPTIONS):
```
$ curl -sS -D - -o /dev/null -X OPTIONS https://api-production-c080.up.railway.app/health \
    -H 'Origin: https://evil.example.com' -H 'Access-Control-Request-Method: GET'
HTTP/2 400
access-control-allow-credentials: true
access-control-allow-methods: DELETE, GET, HEAD, OPTIONS, PATCH, POST, PUT
access-control-max-age: 600
content-type: text/plain; charset=utf-8
vary: Origin
content-length: 22       # body: "Disallowed CORS origin"
```
Simple GET:
```
$ curl -sS -D - -o /dev/null https://api-production-c080.up.railway.app/health \
    -H 'Origin: https://evil.example.com'
HTTP/2 200
access-control-allow-credentials: true
# (NO access-control-allow-origin)
```
=> **No `Access-Control-Allow-Origin`.** Preflight rejected with HTTP 400 ("Disallowed CORS origin").

### PROBE 2 — suffix attack `https://www.riphere.com.evil.com` (+ task-prompt literal `https://www.riphere.com.evil.com`)
```
HTTP/2 400
access-control-allow-credentials: true
vary: Origin
# (NO access-control-allow-origin)
```
=> Not reflected. Suffix-confusion attack blocked.

### PROBE 3 — POSITIVE CONTROL, legit origin `https://www.riphere.com`
```
$ curl ... -X OPTIONS ... -H 'Origin: https://www.riphere.com' -H 'Access-Control-Request-Method: GET'
HTTP/2 200
access-control-allow-credentials: true
access-control-allow-origin: https://www.riphere.com
vary: Origin
```
=> Allowlisted origin IS reflected with credentials. Confirms the middleware is live and the probe
methodology is sound (negative results above are real rejections, not a broken endpoint).

### PROBE 4 — prefix attack `https://evil-riphere.com`
```
HTTP/2 400
access-control-allow-credentials: true
vary: Origin
# (NO access-control-allow-origin)
```
=> Not reflected.

### PROBE 5 — apex `https://riphere.com` (allowlisted)
```
HTTP/2 200
access-control-allow-credentials: true
access-control-allow-origin: https://riphere.com
vary: Origin
```
=> Correctly allowed (matches CORS_ORIGINS).

### ACAO presence sweep across malicious origins (expect 0 hits)
```
$ for o in evil.example.com www.riphere.com.evil.com evil-riphere.com riphere.com.attacker.test; do ... done
  https://evil.example.com                      -> <none>
  https://www.riphere.com.evil.com              -> <none>
  https://evil-riphere.com                      -> <none>
  https://www.riphere.com.evil.com              -> <none>
  https://riphere.com.attacker.test             -> <none>
```

## 4. The `access-control-allow-credentials: true`-on-400 nuance (why it's NOT a finding)

Every response — including the rejected 400s — carries `access-control-allow-credentials: true`.
This is a well-known cosmetic artifact of Starlette's `CORSMiddleware.preflight_response()`, which
seeds the credentials header on the response object **before** the origin allow-check fails. It is
**inert** because:

1. The browser CORS algorithm requires **both** `Access-Control-Allow-Origin` (echoing the exact
   origin) **and** `Access-Control-Allow-Credentials: true` to expose a credentialed response.
2. Here ACAO is **absent** for every non-allowlisted origin, so the browser blocks the response.
3. `Access-Control-Allow-Origin: *` is never emitted (and would be illegal with credentials anyway).

No `Access-Control-Allow-Origin` echo → no credentialed cross-origin read is possible from a
malicious site, regardless of the stray credentials header.

## 5. Verdict

**REFUTED.** A malicious origin is **not** reflected in `Access-Control-Allow-Origin`. With
`CORS_ORIGIN_REGEX` empty in production, only an exact allowlist (`www.riphere.com`, `riphere.com`,
the Railway web URL, localhost) is honored. Credentialed cross-site reads from an attacker-controlled
origin are not possible. The "Allow-Credentials: true on a 400" is a benign Starlette artifact, not
an exploitable misconfiguration.

### Residual / hardening notes (not vulnerabilities)
- `allow_credentials=True` + `allow_methods=["*"]` + `allow_headers=["*"]` is permissive *for
  allowlisted origins only*; safe given the exact allowlist. Risk would materialize only if
  `CORS_ORIGIN_REGEX` were ever set to a loose pattern (e.g. `.*riphere\.com.*` or one with an
  unanchored `.` before a TLD). Recommend: if/when a regex is introduced, anchor it
  (`^https://([a-z0-9-]+\.)?riphere\.com$`) and add a test asserting `*.riphere.com.evil.com` and
  `evil-riphere.com` are rejected.
- The stray `Access-Control-Allow-Credentials: true` on rejected preflights is upstream Starlette
  behavior; cosmetic only.

### Cleanup
None required — all probes were read-only GET/OPTIONS against `/health`. No test data created.
