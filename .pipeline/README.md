# `.pipeline/` — Agentic CI/CD

A CI/CD pipeline **run by a team of specialist Claude agents**, not by static
scripts. Changes to this repo flow through agents that plan, build, review,
secure, test, and release — coordinated by a substrate-agnostic orchestrator.

This is a **persistent, iterated** system: every part of it is
version-controlled in-repo, and the pipeline can improve itself by running its
own changes through the `feature` workflow.

## Layout

```
.pipeline/
├── ARCHITECTURE.md      ← keystone contract (read this first)
├── ROADMAP.md           ← where this is headed
├── agents/              ← agent role definitions (one discipline each)
│   ├── orchestrator.md  architect.md  backend.md  frontend.md
│   └── reviewer.md      security.md   qa.md       release.md
├── workflows/           ← declarative multi-agent DAGs (YAML)
│   ├── feature.yaml  bugfix.yaml  pr-review.yaml  incident.yaml
│   └── README.md
├── orchestrator/        ← the engine (load → validate → plan → execute)
│   └── tests/
└── runs/                ← per-run state + artifacts (run.json, plan.md, …)
```

## The team

| Agent | Discipline | Gate |
|---|---|---|
| `architect` | Decomposes work, writes the plan | — |
| `backend` | FastAPI / SQLAlchemy / Celery | — |
| `frontend` | Next.js / TypeScript | — |
| `reviewer` | Code-review verdict | blocking |
| `security` | AppSec verdict | blocking |
| `qa` | Tests + verdict | blocking |
| `release` | Changelog / merge / deploy | human |
| `orchestrator` | Routing, gates, retries, escalation | — |

## Quickstart

```bash
# Validate a workflow and print its execution plan (no model calls):
python -m orchestrator plan --workflow feature

# Run a workflow end-to-end offline (DryRun executor, no model calls):
python -m orchestrator run --workflow feature \
    --input task_brief=@brief.md --executor dryrun
```

Run from the repo root or from `.pipeline/`. See
[`orchestrator/README.md`](orchestrator/README.md) for details.

## In CI

`.github/workflows/agentic-pipeline.yml` runs the pipeline on GitHub:
- **On every push** — runs the orchestrator's own test suite and a dry-run of
  every workflow spec (the pipeline validating itself).
- **On issue label / PR / manual dispatch** — builds the plan and dispatches
  each agent step to Claude Code (requires the `ANTHROPIC_API_KEY` secret).

## Extending

- **New discipline** → add `agents/<name>.md` (follow ARCHITECTURE.md §3).
- **New pipeline** → add `workflows/<name>.yaml` (follow §5).
- **Engine change** → edit `orchestrator/` (always with tests).

All three are governed by `ARCHITECTURE.md`. Read it before changing anything.
