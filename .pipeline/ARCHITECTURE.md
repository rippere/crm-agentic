# Agentic CI/CD Pipeline — Architecture

> A CI/CD pipeline **run by agents**, not scripts. Work moves through a team of
> specialist Claude agents — each with distinct disciplinary prowess — that
> plan, implement, review, secure, test, and release changes to this repo.
> The system is **persistent**: it lives in-repo as version-controlled
> definitions, and is meant to be iterated on continuously.

This document is the **keystone contract**. Every agent definition
(`agents/*.md`), workflow spec (`workflows/*.yaml`), and the orchestrator
(`orchestrator/`) conform to the schemas defined here.

---

## 1. Mental model

```
   trigger (issue label / PR / manual / cron)
        │
        ▼
   ┌─────────────┐     reads workflow spec + agent defs
   │ ORCHESTRATOR│ ──► builds an execution DAG, resolves gates,
   └─────────────┘     dispatches each step to an Executor
        │
        ▼  (one step = one agent doing one job)
   ┌──────────┐  plan  ┌──────────┐  diff  ┌──────────┐  verdict
   │ Architect│ ─────► │ Backend  │ ─────► │ Reviewer │ ─────►  ...
   └──────────┘        │ Frontend │        │ Security │
                       └──────────┘        │   QA     │
                                           └──────────┘
        │
        ▼
   ┌──────────┐  human-gated
   │ Release  │ ─────────────► merge / tag / deploy
   └──────────┘
```

Three layers, three artifact types:

| Layer | What it is | Where |
|---|---|---|
| **Agents** | Role definitions — a discipline, a model, tools, and a contract | `agents/*.md` |
| **Workflows** | Declarative DAGs that compose agents into a pipeline | `workflows/*.yaml` |
| **Orchestrator** | Engine that validates, plans, and executes a workflow | `orchestrator/` |

The **same definitions** drive both substrates:
- **GitHub Actions** (`.github/workflows/agentic-pipeline.yml`) — real CI/CD,
  agents run as jobs via Claude Code on triggers.
- **Standalone** (`python -m orchestrator run ...`) — run a workflow locally
  or from any runner.

The orchestrator is **substrate-agnostic**: it produces a deterministic
execution plan; an `Executor` decides *how* each step's agent actually runs.

---

## 2. The agent roster (disciplinary prowess)

| Agent | Discipline | Default model | Core job |
|---|---|---|---|
| `orchestrator` | Coordination | opus | Owns the run: routing, gates, retries, escalation. (Meta-agent; see §5.) |
| `architect` | Architecture & planning | opus | Decompose the task; produce an execution **plan** other agents follow. |
| `backend` | Python / FastAPI / Celery | sonnet | Implement API, models, workers, migrations. |
| `frontend` | Next.js / TypeScript | sonnet | Implement App Router UI, components, hooks. |
| `reviewer` | Code review | opus | Correctness + simplification review of the diff; pass/block verdict. |
| `security` | AppSec | opus | Threat-model the diff; find vulns; pass/block verdict. |
| `qa` | Test engineering | sonnet | Author + run tests; assert the change works; pass/block verdict. |
| `release` | DevOps / release | sonnet | Changelog, version, merge/tag/deploy. **Always human-gated.** |

Roster is **open**: add a discipline by dropping a new `agents/<name>.md` and
referencing it from a workflow. Nothing else needs to change.

---

## 3. Agent definition schema (`agents/*.md`)

A markdown file with YAML frontmatter. The frontmatter is machine-read by the
orchestrator; the body is the agent's system prompt.

```yaml
---
name: backend                 # unique id; matches filename
discipline: Backend (Python/FastAPI/Celery)
model: sonnet                 # opus | sonnet | haiku  (maps to claude-* ids at runtime)
tools: [Read, Grep, Glob, Edit, Write, Bash]   # capability allowlist
produces: [diff]              # artifact kinds this agent emits (see §6)
consumes: [plan]              # artifact kinds this agent reads
gate: none                    # none | advisory | blocking | human   (see §4)
escalates_to: orchestrator    # who it hands an unresolvable problem to
max_turns: 40                 # soft budget guardrail
---
```

Required body sections (H2):
`## Mission`, `## Responsibilities`, `## Operating procedure`,
`## Inputs`, `## Outputs`, `## Handoff`, `## Guardrails`,
`## Definition of done`.

---

## 4. Gates

A gate is the quality bar a step must clear before the run proceeds.

| Gate | Meaning |
|---|---|
| `none` | Informational; never blocks. |
| `advisory` | Records a verdict; a non-pass warns but the run continues. |
| `blocking` | A non-`pass` verdict halts the run (after allowed retries). |
| `human` | Run pauses for a human decision before this step's effects land. |

Reviewer/Security/QA default to **blocking**. Release is **human**.
Gates are declared on the agent (default) and overridable per workflow step.

---

## 5. Workflow spec schema (`workflows/*.yaml`)

```yaml
name: feature                       # unique id; matches filename
description: Plan→build→review→secure→test→release for a new feature.
version: 1

trigger:
  on: [issue_labeled, manual]       # issue_labeled | pull_request | manual | schedule
  labels: [agent:feature]           # for issue_labeled
  # cron: "0 6 * * 1"               # for schedule

inputs:                             # named inputs the run is seeded with
  - name: task_brief
    required: true
    description: What to build.

defaults:
  max_retries: 1
  budget_usd: 25                    # soft cap; orchestrator escalates if exceeded

steps:
  - id: plan
    agent: architect
    produces: [plan]

  - id: build-backend
    agent: backend
    depends_on: [plan]
    when: "backend in plan.touches"   # conditional; see §7
    produces: [diff]

  - id: build-frontend
    agent: frontend
    depends_on: [plan]
    when: "frontend in plan.touches"
    produces: [diff]

  - id: review
    agent: reviewer
    depends_on: [build-backend, build-frontend]   # waits for whichever ran
    gate: blocking

  - id: security
    agent: security
    depends_on: [review]
    gate: blocking

  - id: qa
    agent: qa
    depends_on: [review]              # parallel with security
    gate: blocking

  - id: release
    agent: release
    depends_on: [security, qa]
    gate: human
```

Rules the orchestrator enforces:
- Every `agent` referenced must resolve to an `agents/<name>.md`.
- `depends_on` ids must exist; the graph must be acyclic.
- A step `consumes` artifacts produced upstream; the planner verifies the
  producer is an ancestor.
- Steps with no path between them and satisfied deps run **in parallel**.

---

## 6. Artifacts & state

Agents communicate through typed **artifacts** persisted in the run dir.

| Artifact | Produced by | Shape |
|---|---|---|
| `task_brief` | trigger | text/markdown |
| `plan` | architect | markdown + `touches: [backend, frontend, ...]` |
| `diff` | backend/frontend | git diff / changed files |
| `verdict` | reviewer/security/qa | `{ status: pass\|block\|warn, findings: [...] }` |
| `release_note` | release | markdown changelog entry |

A run is a directory: `.pipeline/runs/<run_id>/`
```
run.json            # manifest: workflow, inputs, step states, timings, cost
plan.md             # artifacts, one file per produced artifact
review.verdict.json
...
```
`run.json` is the single source of truth for a run's state and is append-only
per step transition (`pending → running → passed|blocked|skipped|failed`).

---

## 7. Conditional execution (`when`)

`when` is a tiny, safe boolean expression evaluated against produced
artifacts. Supported forms (kept deliberately minimal):
- `<value> in <artifact>.<field>`  e.g. `backend in plan.touches`
- `<artifact>.<field> == <value>`
- `<artifact>.<field> != <value>`
- `always` / `never`

No arbitrary code. The evaluator lives in the orchestrator and is unit-tested.
If a step's `when` is false, it is marked `skipped` and its dependents treat it
as satisfied-but-empty.

---

## 8. Guardrails (non-negotiable)

1. **Human gate on anything that leaves the repo** — merges, tags, deploys,
   and outbound calls are `human` gated by default.
2. **Budget cap** — each run carries a soft `budget_usd`; the orchestrator
   escalates to a human when exceeded rather than silently spending.
3. **Blocking quality gates** — review, security, and QA can stop a release.
   Agents cannot override another agent's blocking verdict; only a human can.
4. **Least privilege** — each agent's `tools` allowlist is the capability
   boundary. Release is the only agent permitted push/merge.
5. **Auditability** — every step writes its prompt, output, and verdict to the
   run dir. Nothing is ephemeral.
6. **Idempotent planning** — the planner is pure: same spec + same artifacts ⇒
   same plan. Execution is the only side-effecting layer.

---

## 9. Execution substrates

### GitHub Actions (`.github/workflows/agentic-pipeline.yml`)
Triggered by issue labels (`agent:feature`, …), PRs, or `workflow_dispatch`.
The job runs the orchestrator to build the plan, then dispatches each agent
step to Claude Code (`anthropic/claude-code-action`) with the agent's system
prompt, tool allowlist, and inputs. Verdicts post back as PR comments/checks.
Requires repo secret `ANTHROPIC_API_KEY`.

### Standalone
```
python -m orchestrator plan  --workflow feature --input task_brief=@brief.md
python -m orchestrator run   --workflow feature --input task_brief=@brief.md \
                             --executor dryrun        # or: claude-code
```
`plan` prints the DAG + execution order and exits. `run` executes via the
chosen `Executor`. `dryrun` records a full run without invoking models — used
in CI to validate every workflow spec on every push.

---

## 10. Iteration model

This pipeline improves itself through itself. To evolve it:
- **Add a discipline** → new `agents/<name>.md`.
- **Add/modify a pipeline** → new/edited `workflows/<name>.yaml`.
- **Change the engine** → `orchestrator/` (always with tests).

Changes to `.pipeline/` are themselves eligible to flow through the `feature`
workflow. `ROADMAP.md` tracks where this is headed; `PROGRESS.md` (repo root)
logs what landed.
