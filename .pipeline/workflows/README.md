# Workflows

Declarative DAGs that compose the agent roster into pipelines. Each spec
conforms to the schema in [`../ARCHITECTURE.md`](../ARCHITECTURE.md) §5 and is
validated by the orchestrator (`python -m orchestrator plan --workflow <name>`).

| Workflow | Trigger | What it does | Gates |
|---|---|---|---|
| `feature` | `issue_labeled` (`agent:feature`), `manual` | Plan → backend/frontend build (parallel, gated by `plan.touches`) → review → security + QA (parallel) → release | review/security/qa **blocking**, release **human** |
| `bugfix` | `issue_labeled` (`agent:bugfix`), `manual` | Quick triage → single-area build → review → optional security (when touched) → QA → release | review/security/qa **blocking**, release **human** |
| `pr-review` | `pull_request` | Review-only: reviewer + security + QA assess the existing diff in parallel. No build, no release | review/security **blocking**, qa **advisory** |
| `incident` | `manual`, `schedule` (cron) | Diagnose → backend/frontend hotfix → review → QA → expedited release | review/qa **blocking**, release **human** |

## How to add a new workflow

1. Create `workflows/<name>.yaml`; set `name` to match the filename, `version: 1`.
2. Pick a `trigger.on` from: `issue_labeled | pull_request | manual | schedule`.
3. Declare `steps`, each with a unique `id` and an `agent` from the roster (§2).
4. Wire `depends_on` (ids must exist, graph must stay acyclic); add `when` only
   in the minimal forms from §7; set `produces` (§6) and `gate` (§4) as needed.
5. Anything leaving the repo (release/merge/deploy) must be `gate: human`.
6. Validate with `python -m orchestrator plan --workflow <name>` before commit.
