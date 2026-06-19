# Orchestrator

The engine for the agentic CI/CD pipeline. It loads agent definitions
(`../agents/*.md`) and workflow specs (`../workflows/*.yaml`), validates them
against the keystone contract (`../ARCHITECTURE.md`), builds a **deterministic
execution plan** (a DAG grouped into parallel waves), and executes that plan
through a pluggable `Executor`.

The orchestrator is **substrate-agnostic**: planning is pure and side-effect
free; an `Executor` decides *how* each step's agent actually runs (offline dry
run, or — in CI — Claude Code).

## Layout

| Module | Responsibility |
|---|---|
| `models.py` | Dataclasses + enums for agents, workflows, gates, run state, model ids. |
| `loader.py` | Parse agent markdown frontmatter and workflow YAML. |
| `validate.py` | Static checks: agent refs, acyclic DAG, consumer/producer reachability, triggers, body sections. |
| `whenexpr.py` | Safe evaluator for the `when` mini-language (§7). No `eval`/`exec`. |
| `planner.py` | Pure `plan()` → topological waves + per-step decisions. |
| `executors.py` | `Executor` ABC, `DryRunExecutor` (offline), `ClaudeCodeExecutor` (stub). |
| `engine.py` | `Runner`: load → validate → plan → execute, honoring gates + budget. |
| `paths.py` | Resolve `.pipeline/{agents,workflows,runs}` robustly. |
| `__main__.py` | CLI (`plan`, `run`). |

## Running

Run from the `.pipeline` directory (so `orchestrator` is importable):

```bash
cd .pipeline

# Validate a workflow and print its DAG + waves + per-step decisions.
python -m orchestrator plan --workflow feature
# exit 0 = valid; exit 1 = validation errors; exit 2 = load error.

# Execute offline (no model calls, $0): writes a run dir under runs/.
python -m orchestrator run --workflow feature \
    --input task_brief=@brief.md \
    --executor dryrun

# Inputs can be inline or read from a file with key=@file.
python -m orchestrator run --workflow bugfix --input task_brief="Fix the login bug"
```

Path overrides: `--agents-dir`, `--workflows-dir`, `--runs-dir`.

## Executor model

`run_step(step, agent, run_dir, artifacts) -> StepState` is the single
side-effecting seam.

- **`DryRunExecutor`** (`--executor dryrun`) — fully working and offline.
  Resolves the prompt (`agent.body` + available inputs), writes it to
  `<run_dir>/<step>.prompt.txt` for auditability, writes a deterministic stub
  artifact for each declared `produces`, gives gated steps a synthetic `pass`
  verdict, and spends `$0`. This is what CI uses to validate every workflow
  spec on every push.
- **`ClaudeCodeExecutor`** (`--executor claude-code`) — a documented **stub**.
  It describes how a step maps to an `anthropic/claude-code-action` /
  Anthropic SDK invocation (model from `agent.model.model_id`, tool allowlist
  from `agent.tools`, prompt from `resolve_prompt`, capped by `max_turns` and
  `budget_usd`) but raises `NotImplementedError` rather than making API calls.
  The live dispatch lives in `.github/workflows/agentic-pipeline.yml`.

## Gates (§4)

The engine honors the effective gate (per-step override, else the agent
default):

- `none` / `advisory` — never halts (advisory records a verdict).
- `blocking` — a non-`pass` verdict halts the run after `defaults.max_retries`.
- `human` — the run pauses cleanly: the step stays `pending` with a
  `needs_human` note, run status becomes `needs_human`, and execution stops.

The run's `budget_usd` is tracked on the manifest; exceeding it escalates to a
human (status `needs_human`). DryRun cost is always `0`.

## Run artifacts (§6)

Each run is a directory `../runs/<workflow>-<UTC timestamp>/` containing:

- `run.json` — the manifest (workflow, inputs, per-step state, timings, cost).
  Re-written after every step transition.
- `<kind>.json` — one file per produced artifact (`plan`, `diff`, `verdict`, …).
- `<step>.prompt.txt` — the resolved prompt for that step.

## Extending

- **Add a discipline** → drop `../agents/<name>.md` (required frontmatter +
  H2 body sections; see ARCHITECTURE §3) and reference it from a workflow.
- **Add/modify a pipeline** → new/edited `../workflows/<name>.yaml` (§5).
- **Add a substrate** → subclass `Executor` and register it in
  `executors.get_executor`.

## Tests

```bash
cd .pipeline && python -m pytest orchestrator -q
```

Tests use small self-contained fixture agents/workflows (in `tests/conftest.py`)
so they do not depend on the real role files.
