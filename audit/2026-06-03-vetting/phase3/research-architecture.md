# NovaCRM External Validation — Phase 3 Research
## Lens: Stack Best Practices 2025-2026 (Supabase Auth in external FastAPI, RLS vs service-role, Next.js App Router + separate Python API, Celery on Railway)

Date: 2026-06-03
Researcher: external-validation subagent
Stack under review: Next.js 16 + FastAPI + Celery + Supabase (auth+Postgres+RLS) + Redis on Railway (4 services).

NOTE ON METHOD: "SOURCE SAYS" = directly stated in a cited source. "INFERENCE" = my reasoning applied to NovaCRM's specific architecture. NovaCRM internal code was NOT inspected in this phase — findings about NovaCRM's *actual* implementation are hypotheses to be confirmed in Phase 2.

---

## TOPIC 1 — Supabase Auth JWT verification in an external FastAPI backend (JWKS, aud, key types)

### Sources
- Supabase Docs, "JSON Web Token (JWT)": https://supabase.com/docs/guides/auth/jwts
- Supabase Docs, "JWT Signing Keys": https://supabase.com/docs/guides/auth/signing-keys
- Supabase Blog, "Introducing JWT Signing Keys": https://supabase.com/blog/jwt-signing-keys
- GitHub Discussion #20763, "Verifying Supabase JWT Myself - Bad Practice?": https://github.com/orgs/supabase/discussions/20763
- objectgraph, "Migrating from Static JWT Secrets to JWKS in Supabase": https://objectgraph.com/blog/migrating-supabase-jwt-jwks/
- anthony lukach, "Securing FastAPI with JWKS (AWS Cognito, Auth0)": https://alukach.com/posts/fastapi-rs256-jwt/
- DEV, "Supabase Auth Introduces Asymmetric JWTs and API Keys Breaking Changes": https://dev.to/kvetoslavnovak/supabase-auth-itroduces-asymmetric-jwts-4i4e

### What sources SAY
- **The `aud` claim MUST be verified and equals `"authenticated"`.** (Docs; Discussion #20763.) In Discussion #20763 the entire thread's resolution was that local verification "fails silently" until you pass `audience="authenticated"`. PyJWT example: `jwt.decode(token, '<jwt_secret>', algorithms=["HS256"], audience="authenticated")`. THIS IS THE #1 SILENT-FAILURE PITFALL for a hand-rolled verifier.
- **Local verification in an external API is explicitly endorsed as common practice.** A Supabase collaborator in #20763: "It is a common thing to do for API's. Almost any jwt library using the secret will decode and verify the jwt." So a FastAPI backend verifying tokens itself is legitimate.
- **Asymmetric (RS256/ES256/EdDSA) is now the recommended/default path; symmetric HS256 is discouraged.** Docs: "We strongly recommend against this [shared-secret] approach… There is almost no benefit from using a JWT signed with a shared secret." Default new asymmetric key is RS256; ECC (ES256, P-256) and Ed25519 optional.
- **JWKS endpoint:** `GET https://<project>.supabase.co/auth/v1/.well-known/jwks.json`. Returns asymmetric keys ONLY ("does not return any keys if you are not using asymmetric JWT signing keys"). With asymmetric keys, verification is LOCAL via WebCrypto/library — no network round trip per request. The `kid` header selects the key.
- **For symmetric (HS256) tokens there is no JWKS;** to validate against the server you must call `GET /auth/v1/user` with the bearer token; HTTP 200 = valid. (Docs.) That is a network round-trip per request — slow.
- **Caching rule (sharp edge):** "Make sure that you do not cache this [JWKS] data for longer… as it might make revocation difficult." Supabase Edge caches JWKS 10 min; client libs may cache another 10 min. Docs explicitly warn: in a key-revocation incident, "your application components may still trust and authenticate JWTs signed with the revoked key… you should ensure you've built a cache busting mechanism as part of your app's backend infrastructure."
- **Algorithm confusion defense (from FastAPI/JWKS pattern, alukach + general JWT security):** Always whitelist `algorithms=["RS256"]` (or ES256). Specifying the algorithm rejects HS256-signed tokens that could exploit a shared secret, and rejects `alg:none`. PyJWT pattern: `jwt.PyJWKClient(jwks_url)` (caches), then `client.get_signing_key_from_jwt(token).key`, then `jwt.decode(..., algorithms=["RS256"], audience=...)`. Install `pyjwt[crypto]` for RSA/ECDSA.
- **`getClaims()` caveat:** `supabase.auth.getClaims()` "is meant to be used only with JWTs issued by Supabase Auth." For custom JWTs use a verification library.
- **Recommended production caching pattern (objectgraph):** "fetch the JWKS on startup, cache the public keys in memory, and on every authenticated request read the `kid`… run ES256 verification locally with no round-trip… only hit the JWKS endpoint again when a key rotates and a `kid` shows up that is not in the cache." But pair with a bounded TTL / cache-bust so revocation works.

### Tradeoffs (local vs remote verification) — from #20763
- Local: lower latency, no network call, one secret/JWKS works for all tokens. CON: cannot detect revoked tokens in real time.
- Remote (`auth.getUser()` / `/auth/v1/user`): handles revocation. CON: network round-trip per request. "Official recommended approach for sensitive operations."

### INFERENCE for NovaCRM
- If NovaCRM's FastAPI still verifies tokens with the **legacy static HS256 secret**, it is on the deprecated path. It also risks the silent `aud` pitfall (must pass `audience="authenticated"`), and — critically — it will BREAK once the project rotates to asymmetric keys / revokes the legacy secret (see Topic 5 timeline). HIGH IMPACT.
- A solo dev verifying HS256 without `aud` check would have a subtly broken/over-permissive verifier (any Supabase-issued token, including ones not meant for this app, could pass). Confirm in Phase 2 whether `aud` and `exp` are actually checked, and whether algorithms are pinned (algorithm-confusion / `alg:none` risk if not).

---

## TOPIC 2 — Supabase RLS vs service-role bypass when a backend mediates

### Sources
- Supabase Docs, "Row Level Security": https://supabase.com/docs/guides/database/postgres/row-level-security
- Supabase Docs, "Why is my service role key client getting RLS errors…": https://supabase.com/docs/guides/troubleshooting/why-is-my-service-role-key-client-getting-rls-errors-or-not-returning-data-7_1K9z
- Supabase Docs, "Securing your API": https://supabase.com/docs/guides/api/securing-your-api
- makerkit, "Supabase RLS Best Practices: Production Patterns for Secure Multi-Tenant Apps": https://makerkit.dev/blog/tutorials/supabase-rls-best-practices
- vibeappscanner, "Supabase Security (2026): RLS, service_role & the CVE-2025-48757 Patterns": https://vibeappscanner.com/supabase-security
- vibeappscanner, "Supabase RLS: Common Mistakes, the (select auth.uid()) Trap & CVE-2025-48757 Breakdown": https://vibeappscanner.com/supabase-row-level-security
- Supabase Blog, "Supabase Security Retro: 2025" (pub Jan 7 2026): https://supabase.com/blog/supabase-security-2025-retro

### What sources SAY
- **service_role ALWAYS bypasses RLS.** "A Supabase client with the Authorization header set to the service role API key will always bypass RLS." "Adding service_role in RLS policies does nothing." So when a backend uses service_role, **RLS provides ZERO tenant isolation** — all authorization must be enforced in application code.
- **THE central pitfall (explicitly stated):** "the main pitfall is assuming that RLS will provide tenant isolation when using service_role credentials in a FastAPI backend — it won't. You must implement explicit authorization checks in your application logic." When service_role mediates, "the backend becomes the access control layer."
- **CVE-2025-48757 (May 2025):** RLS-off-on-public-tables class. vibeappscanner: 10.3% of analyzed Lovable apps shipped public-readable tables because RLS was off. Any table without RLS is "fully exposed via the public API" with the anon/publishable key. (This bites the *direct-from-browser* path, not the service-role path — relevant to NovaCRM only on tables the browser hits directly.)
- **Correct RLS policy idiom:** use `(select auth.uid()) = user_id` (the `select` wrapper is a performance optimization — initplan caching; without it `auth.uid()` re-evaluates per row). Cast UUIDs explicitly; handle NULLs to avoid type-mismatch bypass.
- **2025 secure-by-default changes (Security Retro):** RLS now enabled by default for dashboard-created tables; Data API can be disabled entirely on new projects; custom-schema option; Security Advisors (Splinter linter); visual warnings for tables without RLS; GitHub secret scanning auto-revokes leaked secret keys.
- **service_role hygiene:** server-side only; never in frontend; treat as sensitive env var; rotate if exposed. Edge Functions run as service_role by default and "require validation of authentication in each function."
- **Recommended architecture for a backend-mediated app (Security Retro):** you may "disable the Data API entirely" and treat Supabase like standard Postgres (RDS-style) — i.e., if FastAPI is the ONLY thing touching the DB, the public PostgREST Data API is attack surface you may not need.
- **Breach cost framing (vibeappscanner):** startup breaches cost between $120,000 and $1.24M.

### INFERENCE for NovaCRM (a hybrid where BOTH browser→Supabase AND browser→FastAPI→Supabase may exist)
- **The architecture has TWO authorization regimes that must agree.** Path A: browser → Supabase directly (RLS enforced, `auth.uid()` scopes rows). Path B: browser → FastAPI → Supabase via service_role (RLS BYPASSED, FastAPI must re-derive `user_id` from the verified JWT and filter every query itself). If NovaCRM uses service_role broadly in FastAPI, every single query/endpoint is a manual `WHERE user_id = <jwt sub>` that, if forgotten ONCE, is a cross-tenant data leak. This is the single highest-risk structural property of this stack. HIGH IMPACT.
- A solo dev under time pressure very commonly reaches for service_role "to make it work," silently discarding RLS. Phase 2 must verify: (a) does FastAPI use service_role or a user-scoped client? (b) is there a single choke-point that injects the tenant filter, or is it per-endpoint and forgettable? (c) are demo-mode / AI-feature endpoints (lead scoring, churn, deal-health that read across many contacts) scoped per tenant?
- If RLS is the *only* defense on the browser-direct path while FastAPI bypasses it, the two can drift: a column readable via RLS policy might be exposed differently than via the API. Recommend: keep RLS ON as defense-in-depth even behind the API, and have FastAPI assume a user-scoped connection (set `request.jwt.claims` / use the user's JWT against PostgREST) rather than service_role wherever feasible.

---

## TOPIC 3 — Next.js App Router + separate Python API (when to call Supabase from browser vs through the API)

### Sources
- Next.js Docs (v16.2, updated 2026-03-03), "Backend for Frontend": https://nextjs.org/docs/app/guides/backend-for-frontend
- Next.js Blog, "Building APIs with Next.js": https://nextjs.org/blog/building-apis-with-nextjs
- Supabase Docs, "Auth architecture": https://supabase.com/docs/guides/auth/architecture
- Medium (Ojas Kapre), "Implementing Supabase Authentication with Next.js and FastAPI": https://medium.com/@ojasskapre/implementing-supabase-authentication-with-next-js-and-fastapi-5656881f449b
- GitHub, gvago/nextjs-supabase-ai-template (Next.js + Supabase + FastAPI reference): https://github.com/gvago/nextjs-supabase-ai-template
- DEV (Shayan), "software architecture in Next.js monolith to microservices": https://dev.to/shayan_saed/the-ultimate-guide-to-software-architecture-in-nextjs-from-monolith-to-microservices-i2c

### What sources SAY
- **Next.js is explicit that its backend capabilities are NOT a full backend replacement** — they are "an API layer that is publicly reachable, handles any HTTP request, can return any content type." (BFF guide.) So a separate FastAPI for heavy/complex logic is a sanctioned pattern.
- **Route Handlers are PUBLIC endpoints** — "Any client can access them." Auth is the dev's responsibility. BFF guide: "Always verify credentials before granting access. Do not rely on proxy [middleware] alone for authentication and authorization."
- **Proxy/BFF benefits the guide endorses:** "keeps logic out of the frontend and avoids exposing internal systems"; hide upstream systems; transform/aggregate; offload heavy compute; add validation before forwarding. The guide shows a Route Handler proxying to a backend with `isValidRequest` validation first.
- **Header hygiene warning (BFF guide, Security):** "avoid directly passing incoming request headers to the outgoing response"; sensitive header values appended to response headers "will be visible to clients." And `NextResponse.next({ request: { headers }})` modifies headers the *server* receives and does NOT expose them to the client.
- **Server Component anti-pattern (BFF guide Caveats):** "Fetch data in Server Components directly from its source, not via Route Handlers." Hitting your own Route Handler from a Server Component adds an unnecessary HTTP round-trip (and fails at build time for prerendered components). For Supabase data, fetch directly with the server client in RSCs.
- **Deployment caveat (BFF guide):** if Route Handlers deploy as lambdas, they "cannot share data between requests," may not write to FS, and long-running handlers can be killed by timeouts; WebSockets won't survive. (Relevant if NovaCRM proxies long AI calls through Next.js instead of FastAPI.)
- **The documented Supabase+Next+FastAPI integration pattern (Kapre / template):** Next uses `@supabase/ssr` + `@supabase/supabase-js` to manage sessions client+server; FastAPI verifies the Supabase JWT on protected routes. Browser holds the Supabase session; the same access token is sent to FastAPI as a bearer for verification.

### INFERENCE / synthesis for NovaCRM
- **Decision rule that fits this stack:**
  - Simple, read-mostly, user-owned data with good RLS → call Supabase DIRECTLY from the browser (or from Next.js Server Components/Server Actions using the user-scoped server client). Lower latency, RLS does the authz. (contacts/deals lists, pipeline views.)
  - Anything that needs secrets, third-party orchestration, cross-record computation, or service-role access → go through FastAPI (lead scoring/XGBoost, RoBERTa tagging, Whisper call summaries, GPT-4o email composer, Gmail/Slack connectors, churn/sentiment, deal-health). These are exactly the "complex business rules, sensitive operations, heavy compute" the BFF guide says belong in a real backend.
- **Anti-pattern to check for:** proxying *everything* (including trivial CRUD) through Next.js Route Handlers AND then through FastAPI = three hops, duplicated auth, latency, and lambda-timeout risk. Also, calling your own Route Handler from a Server Component (round-trip you don't need).
- **Two-verifier consistency risk:** the Next.js middleware/server client AND FastAPI both verify Supabase JWTs. They must agree on `aud`, `exp`, and (soon) asymmetric keys. Drift = either a security hole or spurious 401s. Confirm both sides validate identically.
- **CORS / token exposure:** if the browser calls FastAPI directly (riphere.com → api host), CORS must be locked to the app origin, and the Supabase access token is in the browser anyway (it must be, to call FastAPI). That's acceptable for an access token but means token theft via XSS hits both Supabase and FastAPI — Next.js side should keep tokens in httpOnly cookies where it mediates.

---

## TOPIC 4 — Celery reliability on Railway (visibility timeout, redelivery, acks_late, idempotency, beat singleton)

### Sources
- Celery Docs, "Using Redis" (5.6): https://docs.celeryq.dev/en/stable/getting-started/backends-and-brokers/redis.html
- Celery Docs, "Workers Guide" (warm/soft/cold/hard shutdown): https://docs.celeryq.dev/en/stable/userguide/workers.html
- DEV (artemooon), "Celery + Redis at Scale: Designing a Reliable and Efficient Task Queue in Production": https://dev.to/artemooon/celery-redis-at-scale-designing-a-reliable-and-efficient-task-queue-in-production-27nh
- vintasoftware, "Advanced Celery for Django: fixing unreliable background tasks": https://www.vintasoftware.com/blog/guide-django-celery-tasks
- Medium (Bhagya Rana), "Optimizing Celery Retries and Visibility Timeouts at High Scale": https://medium.com/@bhagyarana80/optimizing-celery-retries-and-visibility-timeouts-at-high-scale-aa79f923d880
- Railway Help Station, "Graceful Shutdown of Celery Workers During Deployments": https://station.railway.com/questions/graceful-shutdown-of-celery-workers-duri-7445b567
- Medium (Sudarshan Mondal), "Distributed Scheduling Gone Wrong: The Celery Beat Trap": https://medium.com/@sudarshaana/distributed-scheduling-gone-wrong-the-celery-beat-trap-and-how-we-escaped-85c7e53828f6
- Celery Docs, "Periodic Tasks": https://docs.celeryq.dev/en/stable/userguide/periodic-tasks.html
- django-celery-beat Issue #558 (multiple executions): https://github.com/celery/django-celery-beat/issues/558

### What sources SAY — visibility timeout & redelivery
- **Default Redis visibility timeout = 1 hour.** "The visibility timeout defines the number of seconds to wait for the worker to acknowledge the task before the message is redelivered to another worker."
- **Duplicate-execution rule (Bhagya Rana, concrete):** if a task takes 5 min and visibility_timeout is 3 min, "another worker will pick up the same task at the 3-minute mark" — "silent duplicates" with no exception/log. Fix: `visibility_timeout` MUST exceed your longest task. Example: `visibility_timeout: 600` for 5-min tasks. But don't make it excessively long — that delays redelivery of genuinely lost tasks after a crash.
- **ETA/countdown hazard:** tasks with `countdown`/`eta` longer than visibility_timeout get redelivered repeatedly. "Keep ETA and countdown values shorter than visibility_timeout. If you need longer delays… use Celery Beat." (Celery docs + artemooon.)
- **Even with `acks_late=True`, too-low visibility_timeout still redelivers** (Bhagya Rana) — acks_late does not save you if the broker's visibility window expires mid-task.

### What sources SAY — durability config (artemooon, vintasoftware)
- `task_acks_late = True` — ack only AFTER processing; without it a crash mid-task loses the task.
- `task_reject_on_worker_lost = True` — if worker process is lost, reject (requeue) instead of silently marking done. Pairs with acks_late.
- `worker_prefetch_multiplier = 1` — reserve one task at a time; prevents a busy worker hoarding queued tasks (which would also look like stalls).
- `task_publish_retry = True` + `broker_transport_options.retry_policy` (max_retries ~100, interval_step 2, interval_max 15) — survive broker blips.
- Socket resilience: `socket_keepalive: True`, `retry_on_timeout: True`, `socket_timeout: 5`, `socket_connect_timeout: 5`.
- **Separate Redis instances** for app cache vs broker vs result backend — "a single Redis instance failure took down both the application cache and the task queue, creating a cascade failure."
- **Idempotency is mandatory at scale:** "assume tasks may run twice; design with idempotency in mind." Use dedup keys / task-status checks, or `celery-once` (QueueOnce) Redis lock.
- Time limits: `soft_time_limit` (raises catchable exception for cleanup) + `time_limit` (hard kill) to stop hung tasks blocking worker slots.
- Queue isolation: split heavy/slow jobs from small/critical ones onto dedicated queues+workers; subscribe workers with `-Q`.

### What sources SAY — Celery Beat singleton (the multi-instance trap)
- **Core rule (Celery docs):** "You have to ensure only a single scheduler is running for a schedule at a time, otherwise you'd end up with duplicate tasks." Two beats = duplicate periodic fires (the Mondal article: test users got duplicate emails after ECS scaled beat).
- Options evaluated (Mondal): (1) single dedicated beat = simplest but single point of failure; (2) leader election (risk of missed fires during election); (3) distributed lock / Redlock — chosen — all instances try, only the lock holder runs, no SPOF. RedBeat (Redis-backed scheduler with built-in lock) is the common turnkey form of this.

### What sources SAY — Railway redeploy / SIGTERM (the most Railway-specific risk)
- Railway runs old+new in parallel for `OVERLAP_SECONDS`, then SIGTERM to old; `DRAINING_SECONDS` before hard SIGKILL. (Railway Help Station.)
- Celery shutdown stages: Warm (finish running tasks), Soft (time-limited warm via `worker_soft_shutdown_timeout`, DISABLED by default), Cold, Hard. "If a worker is force-terminated with KILL, currently executing tasks will be lost unless tasks have acks_late." (Celery Workers Guide.)
- **Railway-specific gotchas (Help Station):** if DRAINING_SECONDS < task duration, long tasks are SIGKILLed → if acks_late, they redeliver and re-run (duplicate side effects). "using task_acks_late with task_reject_on_worker_lost can lead to duplicate external API calls if a worker is killed mid-task and another worker immediately picks up the task, unless the task is fully idempotent." Recommendations: trap SIGTERM / use worker_shutdown hook to stop consuming and let tasks finish; **split worker deployments from web deployments so workers aren't restarted on every web deploy**; optionally a "draining" queue so only new workers take new jobs; raise DRAINING_SECONDS above longest task.

### INFERENCE for NovaCRM
- NovaCRM's AI tasks are LONG: Whisper call summarization, GPT-4o email drafting, XGBoost/RoBERTa batch scoring. These are exactly the tasks that (a) exceed a default-ish or mis-set visibility_timeout → silent duplicate model runs (duplicate cost + possibly duplicate emails sent!), and (b) get SIGKILLed on a Railway redeploy → redeliver → re-run. If these tasks call external APIs (OpenAI, Gmail send, Slack post) and are NOT idempotent, a redeploy or a too-short visibility timeout = duplicate outbound emails/Slack messages and double OpenAI spend. HIGH IMPACT.
- With 4 Railway services, is one of them a DEDICATED beat, or is beat embedded in a worker that's horizontally scaled? If beat is not a guaranteed singleton, periodic jobs (e.g., churn recompute, digest emails) double-fire. HIGH IMPACT if any periodic task sends email/Slack.
- Is Redis a Railway Redis with a persistent VOLUME, or ephemeral? See Topic 5.
- Phase 2 checks: (1) explicit `visibility_timeout` >> longest AI task? (2) `task_acks_late` + `task_reject_on_worker_lost` set, AND every external-side-effect task idempotent (dedup key / celery-once)? (3) beat singleton (dedicated service or RedBeat lock)? (4) worker deploy decoupled from web deploy, SIGTERM trapped, DRAINING_SECONDS raised? (5) broker vs result-backend vs cache on separate Redis (or at least separate DB index)?

---

## TOPIC 5 — Cross-cutting time bombs specific to THIS stack on Railway

### A) Supabase legacy-key deprecation timeline (HARD dates) — affects Topics 1 & 2
Sources: https://supabase.com/blog/jwt-signing-keys ; https://supabase.com/docs/guides/auth/signing-keys ; https://supabase.com/blog/supabase-security-2025-retro ; https://github.com/orgs/supabase/discussions/40300
- **Oct 1, 2025:** all NEW projects default to asymmetric JWTs. Existing projects' legacy JWT secret auto-migrated into the new signing-keys system (still works until you rotate/revoke).
- **Nov 1, 2025:** projects restored after this date come back WITHOUT legacy `anon`/`service_role` keys; new projects no longer have anon/service_role for use; reminders to switch to publishable/secret keys begin.
- **Late 2026 (HARD):** "All projects will be required to move away from `anon` and `service_role` keys and use the new API keys instead."
- Rotation model: standby → current → previously-used → revoked, zero-downtime, reversible. After you REVOKE the legacy secret, "anon, service_role and any JWTs signed with the old secret will be rejected. Only JWTs signed with the new asymmetric key will be accepted."
- **The break condition for NovaCRM:** a FastAPI backend that verifies with the static HS256 secret, OR uses the literal `service_role`/`anon` keys, will start rejecting valid tokens / lose DB access the moment the project rotates to asymmetric + revokes legacy, and is on a forced-migration clock to late 2026. Asymmetric verification ALSO requires a JWKS cache-bust mechanism (Docs warn the multi-layer 10+10 min cache can keep trusting a revoked key during an incident). HIGH IMPACT.

### B) Railway Redis persistence — affects Topic 4
Sources: https://station.railway.com/questions/critical-data-loss-issue-ephemeral-sto-5f150da4 ; https://railway.com/deploy/dragonfly-redis-alternative
- "Ephemeral storage is lost at redeploy; to persist data between deployments you'll need to use Volumes." A Redis/Dragonfly without a `/data` volume "runs in ephemeral mode and all data is lost on restart." Documented 2025 case: complete data loss on every version upgrade due to ephemeral storage.
- **For NovaCRM:** if the Celery broker Redis has no persistent volume (or AOF/RDB off), every Railway redeploy can drop QUEUED-but-unstarted tasks (lead-scoring jobs, scheduled digests). Even with acks_late (which only protects in-flight, acknowledged-late tasks via redelivery), messages sitting in the queue at restart can vanish if Redis state isn't persisted. Confirm: broker Redis has a volume + persistence, or accept that queued work is lost on deploy and design enqueue to be replayable.

---

## SURPRISES / non-obvious
1. The `aud="authenticated"` omission causes SILENT verification failure (not an error) — the most common Supabase-JWT bug, and an over-permissive verifier if the algorithm isn't pinned.
2. `acks_late=True` does NOT protect against a too-short visibility_timeout — the broker redelivers mid-task regardless, causing duplicate runs. Two independent settings, both required.
3. Railway's redeploy SIGTERM→SIGKILL window, combined with acks_late + non-idempotent tasks, is a *duplicate-side-effect generator* (double emails / double OpenAI spend) on EVERY deploy — and the standard advice is to decouple worker deploys from web deploys, which a solo dev on Railway likely hasn't done.
4. Supabase has a HARD late-2026 deadline to abandon `anon`/`service_role` + static HS256; an external FastAPI verifier on the legacy path is a dated time bomb, not just a style issue.
5. With service_role in the backend, RLS contributes NOTHING to tenant isolation — yet the landing page leans on Supabase RLS as if it's the safety net. If FastAPI bypasses RLS and forgets a tenant filter once, that's the breach.
6. Beat double-firing is invisible until someone notices duplicate periodic emails — exactly NovaCRM's churn/digest/notification surface.

## IMPLICATIONS FOR NOVACRM (condensed)
- Pin down the auth model FIRST (Phase 2): HS256-static vs asymmetric-JWKS; `aud`+`exp`+alg checks; legacy vs new API keys. This gates a known break by late 2026 and current correctness.
- Determine whether FastAPI uses service_role (RLS bypassed → manual authz everywhere) or a user-scoped client; find the tenant-filter choke point or prove it's missing.
- Audit Celery: explicit visibility_timeout vs longest AI task; acks_late + reject_on_worker_lost; idempotency on every email/Slack/OpenAI side-effect; beat singleton; worker/web deploy decoupling; Redis persistence volume.
- Decide the browser-direct-vs-FastAPI boundary deliberately; eliminate triple-hop proxying and Server-Component→own-Route-Handler round-trips; ensure both JWT verifiers agree.
- The SOC 2 / GDPR landing-page claims raise the stakes on the service_role/RLS and duplicate-side-effect findings: cross-tenant leakage or duplicated outbound email are exactly the control failures those claims assert don't happen.
