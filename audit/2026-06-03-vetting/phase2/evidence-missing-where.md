# NovaCRM Phase 2 — Missing Tenant Scoping Sweep (`apps/api/app/routers/*.py`)

Authorized internal security validation (product owner's own infra).
Scope: every handler that touches a workspace-owned table
(`contacts, deals, tasks, projects, messages, call_summaries, activity_events,
clarity_scores, connectors, agents`). For each, determine whether it filters by
the caller's `workspace_id`.

## How scoping is enforced in this codebase (baseline)

- Auth dependency: `get_current_user` (`app/dependencies.py:18`) resolves the
  `User` row from the verified Supabase JWT; `current_user.workspace_id` is the
  authoritative tenant id.
- The dominant, **correct** pattern in every `/workspaces/{workspace_id}/...`
  route is a two-part guard:
  1. `if current_user.workspace_id != workspace_id: raise 403` (path param can't
     be used to reach another tenant), **and**
  2. every query carries `.where(<Model>.workspace_id == workspace_id)`.
- Routes that use the "no path param" idiom (`agents.py`, `mcp_server.py`) instead
  filter directly on `current_user.workspace_id`.

A handler is **scoped = yes** only if the row set it reads/writes is constrained
to the caller's workspace. A handler is **scoped = no** if a row from another
workspace can be read or written.

---

## RESULT TABLE

Legend: WS = `workspace_id`. "scoped" = does the data access filter by caller's WS.

### agents.py
| endpoint | method | table | scoped | evidence (file:line) |
|---|---|---|---|---|
| `/agents` | GET | agents | yes | agents.py:45 `.where(Agent.workspace_id == current_user.workspace_id)` |
| `/agents/{agent_id}/run` | POST | agents, activity_events | yes | agents.py:58 `.where(Agent.id==…, Agent.workspace_id==current_user.workspace_id)`; event written with `workspace_id=current_user.workspace_id` (72) |
| `/agents/{agent_id}` | PATCH | agents | yes | agents.py:100 `.where(Agent.id==…, Agent.workspace_id==current_user.workspace_id)` |
| **`/jobs/{job_id}`** | **GET** | **(Celery result → contacts/deals/messages data)** | **NO** | **agents.py:115-134 — handler takes only `job_id`; body never references `workspace_id`/`current_user`; returns `task.result` for ANY job_id. See FINDING 1.** |

### mcp_server.py  (no path param idiom; scopes on `current_user.workspace_id`)
| endpoint | method | table | scoped | evidence (file:line) |
|---|---|---|---|---|
| `/mcp` → tool `list_contacts` | POST | contacts | yes | mcp_server.py:94 `.where(Contact.workspace_id == workspace_id)` where `workspace_id = current_user.workspace_id` (251) |
| `/mcp` → tool `list_deals` | POST | deals | yes | mcp_server.py:123 `.where(Deal.workspace_id == workspace_id)` (wid from 251) |
| `/mcp` → tool `stale_deals` | POST | deals | yes | mcp_server.py:147-150 `.where(Deal.workspace_id == workspace_id, …)` |
| `/mcp` → tool `pipeline_summary` | POST | deals | yes | mcp_server.py:170 `.where(Deal.workspace_id == workspace_id)` |

`workspace_id` is taken from `current_user.workspace_id` at mcp_server.py:251 and
None is rejected (252-253). The MCP server is correctly scoped.

### contacts.py  (all guarded by `current_user.workspace_id != workspace_id` 403 + WS-filtered query)
| endpoint | method | table | scoped | evidence (file:line) |
|---|---|---|---|---|
| `/workspaces/{wid}/contacts` | POST | contacts, activity_events | yes | guard 61; insert `workspace_id=workspace_id` 72 |
| `/workspaces/{wid}/contacts` | GET | contacts | yes | guard 104; `.where(Contact.workspace_id==workspace_id)` 107 |
| `/workspaces/{wid}/contacts/export` | GET | contacts | yes | guard 129; `.where(... workspace_id==workspace_id)` 132 |
| `/workspaces/{wid}/contacts/import` | POST | contacts | yes | guard 162; upsert `.where(workspace_id==workspace_id, email==…)` 193-196; insert WS 211 |
| `/workspaces/{wid}/contacts/{cid}/score` | POST | contacts | yes | guard 233; `.where(Contact.id==…, workspace_id==workspace_id)` 237 |
| `/workspaces/{wid}/contacts/{cid}/compose` | POST | contacts | yes | guard 268; `.where(id==…, workspace_id==workspace_id)` 272; REST fallback also filters `workspace_id` 278 |
| `/workspaces/{wid}/contacts/{cid}/enrich` | POST | contacts | yes | guard 343; `.where(id==…, workspace_id==workspace_id)` 347; fallback 351 |
| `/workspaces/{wid}/contacts/{cid}` | GET | contacts | yes | guard 368; `.where(id==…, workspace_id==workspace_id)` 372 |
| `/workspaces/{wid}/contacts/{cid}` | PATCH | contacts, activity_events | yes | guard 398; `.where(id==…, workspace_id==workspace_id)` 402 |
| `/workspaces/{wid}/contacts/{cid}` | DELETE | contacts, activity_events | yes | guard 443; `.where(id==…, workspace_id==workspace_id)` 447 |
| `/workspaces/{wid}/contacts/{cid}/status` | PATCH | contacts, activity_events | yes | guard 479; `.where(id==…, workspace_id==workspace_id)` 487 |
| `/workspaces/{wid}/contacts/{cid}/send-email` | POST | contacts, connectors, activity_events | yes | guard 524; connector `.where(workspace_id==workspace_id, service=='gmail')` 532 |
| `/workspaces/{wid}/contacts/{cid}/timeline` | GET | messages, call_summaries, deals, activity_events | yes | guard 574; every sub-query filters `workspace_id==workspace_id` (587, 605, 621, 640) |
| `/workspaces/{wid}/contacts/{cid}/brief` | POST | contacts, messages, call_summaries, deals | yes | guard 669; all queries WS-filtered (680, 688, 696, 704) |

### deals.py  (all guarded + WS-filtered)
| endpoint | method | table | scoped | evidence (file:line) |
|---|---|---|---|---|
| `/workspaces/{wid}/deals` | GET | deals | yes | guard 50; `.where(Deal.workspace_id==workspace_id)` 53 |
| `/workspaces/{wid}/deals/export` | GET | deals | yes | guard 70; `.where(... workspace_id==workspace_id)` 73 |
| `/workspaces/{wid}/deals/health` | POST | deals (via worker) | yes | guard 104 (require_admin); worker enqueued with `str(workspace_id)` 109 |
| `/workspaces/{wid}/deals/stale` | GET | deals | yes | guard 121; `.where(workspace_id==workspace_id, …)` 129 |
| `/workspaces/{wid}/deals/history` | GET | deals | yes | guard 167; `.where(workspace_id==workspace_id, stage=='closed_won')` 171-173 |
| `/workspaces/{wid}/pipeline/suggestions` | GET | deals | yes | guard 205; `.where(workspace_id==workspace_id, …)` 210 |
| `/workspaces/{wid}/pipeline/optimize` | POST | deals (via worker) | yes | guard 256 (require_admin); worker `str(workspace_id)` 260 |
| `/workspaces/{wid}/deals` | POST | deals, activity_events | yes | guard 294; insert `workspace_id=workspace_id` 298 |
| `/workspaces/{wid}/deals/{deal_id}` | GET | deals | yes | guard 332; `.where(id==…, workspace_id==workspace_id)` 336 |
| `/workspaces/{wid}/deals/{deal_id}` | PATCH | deals, activity_events | yes | guard 352; `.where(id==…, workspace_id==workspace_id)` 356 |
| `/workspaces/{wid}/deals/{deal_id}/timeline` | GET | deals, activity_events | yes | guard 393; deal `.where(id==…, workspace_id==workspace_id)` 397; events `.where(workspace_id==workspace_id)` 403 |
| `/workspaces/{wid}/deals/{deal_id}` | DELETE | deals, activity_events | yes | guard 436; `.where(id==…, workspace_id==workspace_id)` 440 |
| `/workspaces/{wid}/deals/bulk` | POST | deals, activity_events | yes | guard 482; `.where(workspace_id==workspace_id, Deal.id.in_(ids))` 499-501 — IDs intersected with WS |
| `/workspaces/{wid}/deals/{deal_id}/probability-trend` | GET | deals | yes | guard 551; `.where(id==…, workspace_id==workspace_id)` 555 |

### search.py  (all guarded + WS-filtered, incl. raw SQL)
| endpoint | method | table | scoped | evidence (file:line) |
|---|---|---|---|---|
| `/workspaces/{wid}/contacts/search` | GET | contacts | yes | guard 34; count SQL `WHERE workspace_id = :wid` 45-47; vector SQL `WHERE workspace_id = :wid` 57-58; ORM fallback `.where(Contact.workspace_id==workspace_id, …)` 85 |
| `/workspaces/{wid}/contacts/embed` | POST | contacts (via worker) | yes | guard 118; worker `str(workspace_id)` 123 |
| `/workspaces/{wid}/contacts/embed-all` | POST | contacts (via worker) | yes | guard 137; count SQL `WHERE workspace_id = :wid` 140-142; worker `str(workspace_id)` 147 |

### calls.py  (all guarded + WS-filtered)
| endpoint | method | table | scoped | evidence (file:line) |
|---|---|---|---|---|
| `/workspaces/{wid}/calls/upload` | POST | call_summaries | yes | guard 53; insert `workspace_id=workspace_id` 84 |
| `/workspaces/{wid}/calls` | GET | call_summaries | yes | guard 108; `.where(CallSummary.workspace_id==workspace_id)` 115 |
| `/workspaces/{wid}/calls/{call_id}` | GET | call_summaries | yes | guard 143; `.where(id==…, workspace_id==workspace_id)` 147-149 |
| `/workspaces/{wid}/calls/{call_id}` | DELETE | call_summaries | yes | guard 178; `.where(id==…, workspace_id==workspace_id)` 182-184 |

> Note (call_summaries access): the call list/detail/delete are correctly scoped
> here; the cross-tenant call-summary exposure risk is **indirect**, via the result
> of a transcription/processing job retrieved through `GET /jobs/{id}` (FINDING 1).

### tasks.py  (all guarded + WS-filtered)
| endpoint | method | table | scoped | evidence (file:line) |
|---|---|---|---|---|
| `/workspaces/{wid}/tasks` | GET | tasks | yes | guard 75; `.where(Task.workspace_id==workspace_id)` 78 |
| `/workspaces/{wid}/tasks` | POST | tasks | yes | guard 94; insert `workspace_id=workspace_id` 98 |
| `/workspaces/{wid}/tasks/by-external/{external_id}` | PUT | tasks | yes | guard 134; `.where(workspace_id==workspace_id, external_id==…)` 138; insert WS 143 |
| `/workspaces/{wid}/tasks/{task_id}` | DELETE | tasks | yes | guard 171; `.where(id==…, workspace_id==workspace_id)` 175 |
| `/workspaces/{wid}/tasks/{task_id}` | PUT | tasks | yes | guard 193; `.where(id==…, workspace_id==workspace_id)` 197 |

### projects.py  (all guarded + WS-filtered)
| endpoint | method | table | scoped | evidence (file:line) |
|---|---|---|---|---|
| `/workspaces/{wid}/projects` | GET | projects | yes | guard 73; `.where(Project.workspace_id==workspace_id)` 76 |
| `/workspaces/{wid}/projects` | POST | projects | yes | guard 88; insert `workspace_id=workspace_id` 91 |
| `/workspaces/{wid}/projects/{project_id}` | GET | projects | yes | guard 110; `.where(id==…, workspace_id==workspace_id)` 113 |
| `/workspaces/{wid}/projects/{project_id}` | PATCH | projects | yes | guard 129; `.where(id==…, workspace_id==workspace_id)` 132 |
| `/workspaces/{wid}/projects/by-external/{external_id}` | PUT | projects | yes | guard 164; `.where(workspace_id==workspace_id, external_id==…)` 168; insert WS 173 |
| `/workspaces/{wid}/projects/{project_id}` | DELETE | projects | yes | guard 197; `.where(id==…, workspace_id==workspace_id)` 200 |

### messages.py  (all guarded + WS-filtered)
| endpoint | method | table | scoped | evidence (file:line) |
|---|---|---|---|---|
| `/workspaces/{wid}/messages/{message_id}/score-clarity` | POST | messages, clarity_scores | yes | guard 74; `.where(Message.id==…, workspace_id==workspace_id)` 79; clarity_score insert `workspace_id=workspace_id` 96 |
| `/workspaces/{wid}/messages` | GET | messages, clarity_scores, tasks | yes | guard 121; `.where(Message.workspace_id==workspace_id)` 126 |
| `/workspaces/{wid}/messages/reprocess` | POST | messages (via worker) | yes | guard 153; worker `str(workspace_id)` 158 |

### events.py  (all guarded + WS-filtered)
| endpoint | method | table | scoped | evidence (file:line) |
|---|---|---|---|---|
| `/workspaces/{wid}/activity` | GET | activity_events | yes | guard 52; `.where(ActivityEvent.workspace_id==workspace_id)` 57 |
| `/workspaces/{wid}/activity` | POST | activity_events | yes | guard 71; insert `workspace_id=workspace_id` 75 |
| `/workspaces/{wid}/events` (SSE) | GET | activity_events | yes | guard 108; seed `.where(workspace_id==workspace_id)` 115; stream loop `.where(workspace_id==workspace_id, created_at>…)` 131 |

### ai.py
| endpoint | method | table | scoped | evidence (file:line) |
|---|---|---|---|---|
| `/workspaces/{wid}/ai/query` | POST | contacts, deals, tasks, activity_events | yes | guard 52; contact count `.where(Contact.workspace_id==workspace_id)` 60; deals `.where(workspace_id==workspace_id)` 65; tasks `.where(workspace_id==workspace_id, …)` 71; events `.where(workspace_id==workspace_id)` 76 |

### gmail.py  (connectors)
| endpoint | method | table | scoped | evidence (file:line) |
|---|---|---|---|---|
| `/workspaces/{wid}/connectors/gmail/auth` | GET | connectors | yes | guard 112; no data read (builds OAuth URL) |
| `/auth/gmail/callback` | GET | connectors | yes (by design) | workspace_id derived from **signed** state `verify_state(state)` 141; upsert `.where(workspace_id==workspace_id, service, external_email)` 181-185 |
| `/workspaces/{wid}/connectors/gmail/sync` | POST | connectors | yes | guard 219; `.where(workspace_id==workspace_id, service=='gmail')` 223 |
| `/workspaces/{wid}/connectors` | GET | connectors, activity_events | yes | guard 248; `.where(Connector.workspace_id==workspace_id)` 252; status helper filters `connector.workspace_id` 63 |
| `/workspaces/{wid}/connectors/{connector_id}/status` | GET | connectors | yes | guard 274; `.where(id==…, workspace_id==workspace_id)` 277-280 |
| `/workspaces/{wid}/connectors/gmail/subscribe` | POST | connectors | yes | guard 316; `.where(workspace_id==workspace_id, service=='gmail')` 325 |
| `/webhooks/gmail/push` | POST | connectors | yes (by design) | unauthenticated webhook; verified by shared secret 428; matches connector by `external_email` (Google-asserted) 387-392 — no caller-supplied WS, no cross-tenant read |
| `/workspaces/{wid}/connectors/{connector_id}` | DELETE | connectors | yes | guard 460; `.where(id==…, workspace_id==workspace_id)` 463-466 |

### slack.py  (connectors)
| endpoint | method | table | scoped | evidence (file:line) |
|---|---|---|---|---|
| `/workspaces/{wid}/connectors/slack/auth` | GET | connectors | yes | guard 69; no data read |
| `/auth/slack/callback` | GET | connectors | yes (by design) | WS from **signed** state `verify_state(state)` 92; upsert `.where(workspace_id==workspace_id, …)` 135-138 |
| `/workspaces/{wid}/connectors/slack/sync` | POST | connectors | yes | guard 169; `.where(workspace_id==workspace_id, service=='slack')` 172 |
| `/webhooks/slack/events` | POST | connectors | yes (by design) | unauth webhook; HMAC-verified 262; matches connector by Slack-asserted `team_id` 223-230 — no caller-supplied WS |

### slack_interactions.py  (HITL approval)
| endpoint | method | table | scoped | evidence (file:line) |
|---|---|---|---|---|
| `/slack/interactions` → event lookup | POST | activity_events | **NO (global lookup)** | slack_interactions.py:240-244 `.where(type=='hitl_pending', meta LIKE %hitl_id%)` — **no workspace_id filter**; event found across ALL workspaces. See FINDING 2. |
| `/slack/interactions` → `_handle_approve` contact update | POST (bg task) | contacts | **NO (write)** | slack_interactions.py:173-180 `.where(Contact.id == contact_id)` — **no workspace_id filter**; writes `contact.last_activity` to a contact identified only by id from event meta. See FINDING 2. |
| `/slack/interactions` → `_handle_approve` connector | POST (bg task) | connectors | yes | connector `.where(workspace_id==workspace_id, service=='gmail')` 96-99 (workspace_id from event meta 92) |

> The `/slack/interactions` data access is gated behind a **fail-closed** Slack
> HMAC signature check (slack_interactions.py:44 — rejects when
> `SLACK_SIGNING_SECRET` unset; 207 enforces). `hitl_id` and `contact_id` come
> from server-minted event meta, not raw attacker input, and `hitl_id` is
> re-canonicalised to block LIKE-wildcard injection (231-234). So the missing
> `workspace_id` filters here are a **latent / defense-in-depth** scoping gap
> rather than a directly reachable cross-tenant attack from an external client.

### workspaces.py / auth.py  (workspace + user provisioning — not workspace-owned-table reads)
| endpoint | method | table | scoped | evidence (file:line) |
|---|---|---|---|---|
| `/workspaces/{wid}` | GET | workspaces | yes | guard 42; reads own workspace row 45 |
| `/workspaces/{wid}` | PATCH | workspaces | yes | guard 59; 62 |
| `/workspaces` | POST | workspaces, agents | yes | binds new WS to `current_user`; seeds agents under new ws_id 97-98 |
| `/auth/verify` | POST | users, workspaces, agents | n/a | provisioning from verified JWT; scoped to `supabase_uid` 79 |
| `/me` | GET | users | yes | returns own `current_user` 119-123 |
| `/workspaces/{wid}/invite` | POST | (Supabase admin) | yes | guard 143 + admin check 146 |

---

## FINDINGS (unscoped read/write)

### FINDING 1 — `GET /jobs/{job_id}` returns ANY workspace's Celery job result (unscoped read) — HIGH

**File:** `apps/api/app/routers/agents.py:115-134`

```python
@router.get("/jobs/{job_id}", response_model=JobStatusResponse)
async def get_job_status(
    job_id: str,
    current_user: User = Depends(get_current_user),   # <-- auth only; NEVER used below
) -> JobStatusResponse:
    from app.workers.celery_app import celery_app
    task = celery_app.AsyncResult(job_id)             # keyed solely by job_id
    state = task.state
    ...
    if state == "SUCCESS":
        raw = task.result                              # <-- another tenant's result
        result = raw if isinstance(raw, dict) else {"value": str(raw)}
    ...
    return JobStatusResponse(job_id=job_id, state=state, result=result, error=error)
```

The handler authenticates the caller but performs **no workspace check** and has
**no DB lookup tying the job to a workspace**. It returns `task.result` for any
`job_id`. The Celery result backend (Redis) is global across all tenants.

Worker result payloads carried by this endpoint include cross-tenant data, e.g.:
- `score_contact.py:117` → `{"contact_id": …, "ml_score": {…signals incl. revenue…}}`
- `ingest.py:428` → `{"message_id": …, "new_tasks": N}`; `ingest.py:328/563` return dicts
- `deal_health_worker.py:108` → `{"workspace_id": …, "deals_scored": …, "alerts_fired": …}`
- `embed_contacts.py:55`, `pipeline.py:100` → `{"workspace_id": …, …}`
- `transcribe.py` (call summaries) result is likewise retrievable here.

`job_id`s are server-minted UUIDv4 returned to the enqueuing client from many
endpoints (e.g. contacts `/score` 247, calls `/upload` 99, deals `/health` 110,
`/pipeline/optimize` 261, messages `/reprocess` 159, search embeds). Any
authenticated user who obtains/guesses another tenant's job_id reads that job's
result. Note the `result` field itself is `Optional` (only populated on SUCCESS),
so the leak is the job result payload, not arbitrary table dumps — but it is a
true cross-tenant disclosure.

**DYNAMIC PROOF (executed against the live `crm-redis` result backend):**

PoC file: `/tmp/novacrm-audit/poc_jobs_idom.py` — reproduces the verbatim handler
body (agents.py:121-134), stores a Workspace-A `score_lead` result in the same
Redis backend the app uses, then calls the handler as a Workspace-B caller.

Command:
```
/tmp/novacrm-audit/poc-venv/bin/python /tmp/novacrm-audit/poc_jobs_idom.py
```

Observed output:
```
[setup] Stored WORKSPACE A job result in crm-redis result backend
        job_id = AUDIT-9b486595-0a3f-4b1f-9c1d-7319c6e456c1

[attack] Caller authenticated to WORKSPACE B: bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb
[attack] Requests GET /jobs/AUDIT-9b486595-0a3f-4b1f-9c1d-7319c6e456c1

[RESULT] Handler response returned to the WORKSPACE B caller:
{
  "job_id": "AUDIT-9b486595-0a3f-4b1f-9c1d-7319c6e456c1",
  "state": "SUCCESS",
  "result": {
    "contact_id": "11111111-1111-1111-1111-111111111111",
    "ml_score": {
      "value": 87, "label": "hot", "trend": "stable",
      "signals": ["Active customer (+10)", "High revenue $250,000 (+5)",
                  "[workspace A PRIVATE] CEO @ AcmeCorp, deal $250k"]
    }
  },
  "error": null
}

[VERDICT] Cross-tenant data disclosed to workspace B with NO workspace check: True
[cleanup] Removed test job result; key still present?: False
```

The Workspace-B caller received Workspace-A's private result. The handler logic is
pure (Celery `AsyncResult` only), so reproducing the handler body against the real
backend is faithful to production behavior. Test key was namespaced (`AUDIT-` prefix)
and deleted; cleanup confirmed (`key still present?: False`). No real data touched.

**Exploitability:** authenticated IDOR. Requires the victim's `job_id`
(high-entropy UUIDv4), which is **not enumerable** but is disclosed to whoever
triggered the job and may leak via logs, the request-logging middleware
(`main.py:106` logs `path` including the job_id), shared screenshots, browser
history, or referrers. Real attacker preconditions: a valid account in any
workspace + knowledge of a foreign job_id. This bounds it below a trivial
sequential-IDOR but it remains a genuine cross-tenant disclosure.

**Remediation:** persist a `job → workspace_id` (and ideally `job → user`)
mapping at enqueue time (e.g. a `jobs` table or a Redis key namespaced by
workspace), and in `get_job_status` verify the job belongs to
`current_user.workspace_id` before returning `task.result`; else 404. Do **not**
rely on UUID unguessability as the control.

---

### FINDING 2 — `/slack/interactions` HITL handler: event + contact accessed without workspace filter (latent unscoped read/write) — LOW

**File:** `apps/api/app/routers/slack_interactions.py`

1. Pending-event lookup is **global** (no `workspace_id`):
   ```python
   # slack_interactions.py:240-244
   select(ActivityEvent).where(
       ActivityEvent.type == "hitl_pending",
       ActivityEvent.meta.like(f'%"hitl_id": "{hitl_id}"%'),
   ).limit(1)
   ```
2. The approve path then loads + **writes** a contact filtered by id only:
   ```python
   # slack_interactions.py:173-180
   select(Contact).where(Contact.id == contact_id)   # no workspace_id
   ...
   contact.last_activity = f"Email sent {now_label}"  # write
   ```
   (`contact_id` comes from the event's `meta`, not a path/body param.)

**Why this is LOW, not HIGH (honest assessment):**
- The endpoint is gated by a **fail-closed** Slack HMAC signature check
  (`slack_interactions.py:44` returns `False` when `SLACK_SIGNING_SECRET` is unset;
  enforced at 207). An external client cannot reach the handler logic without a
  valid Slack signature.
- `hitl_id` is re-parsed to canonical UUID form (231-234), preventing LIKE-wildcard
  injection, and both `hitl_id` and `contact_id` originate from server-minted event
  `meta`, not raw attacker input.
- Because the workspace is implied by the matched event's own `meta`
  (`_handle_approve` uses `meta["workspace_id"]` for the connector lookup, 92-99),
  the missing `workspace_id` predicate does not, by itself, give an external Slack
  caller a way to act on another tenant's contact.

I could **not** demonstrate a reachable cross-tenant exploit here from an external
client (the signature gate blocks it), so this is reported as a **latent /
defense-in-depth scoping gap**, not a proven exploit. It should still be fixed:
add `ActivityEvent.workspace_id == <ws from meta>` to the event lookup and
`Contact.workspace_id == <ws from meta>` to the contact lookup so a future
code path (or a malformed/forged event meta) can't write across tenants.

**Remediation:** thread the workspace through both queries; verify the resolved
contact's `workspace_id` matches the event's `meta["workspace_id"]` before writing.

---

## SUMMARY

- Handlers reviewed touching workspace-owned tables: **all** routers in
  `apps/api/app/routers/*.py`.
- **Correctly scoped:** every endpoint in contacts.py, deals.py, search.py,
  calls.py, tasks.py, projects.py, messages.py, events.py, ai.py, gmail.py,
  slack.py, workspaces.py, auth.py, mcp_server.py, and 3 of 4 agents.py endpoints.
  `agents.py` and `mcp_server.py` (the "no path param" routers) are properly
  scoped on `current_user.workspace_id`.
- **Unscoped — FINDING 1 (HIGH, PROVEN dynamically):** `GET /jobs/{job_id}`
  (agents.py:115-134) — cross-tenant Celery job-result disclosure, demonstrated
  live against crm-redis.
- **Unscoped — FINDING 2 (LOW, latent / not externally reachable):**
  `/slack/interactions` event + contact access (slack_interactions.py:240-244 read,
  173-180 read+write) lack a `workspace_id` filter, but are gated behind fail-closed
  HMAC verification with server-minted identifiers; no reachable exploit shown.
