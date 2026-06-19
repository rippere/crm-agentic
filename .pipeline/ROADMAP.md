# Agentic Pipeline — Roadmap

This pipeline is built to be iterated on. This file tracks where it's headed;
landed work is logged in the repo-root `PROGRESS.md`.

## ✅ Iteration 1 — Foundation (current)

The scaffold a team can build on:
- [x] Keystone architecture contract (`ARCHITECTURE.md`)
- [x] 8 agent role definitions with least-privilege tool allowlists
- [x] 4 declarative workflows: `feature`, `bugfix`, `pr-review`, `incident`
- [x] Substrate-agnostic orchestrator: load → validate → plan → execute
- [x] `DryRunExecutor` (full offline runs) + `ClaudeCodeExecutor` (stub)
- [x] Safe `when:` expression evaluator (no eval/exec)
- [x] GitHub Actions wiring + self-validating CI (specs tested on every push)
- [x] Run state + artifact persistence (`runs/<run_id>/run.json`)

## 🔜 Iteration 2 — Real execution

Make agents actually run, not just plan:
- [ ] Implement `ClaudeCodeExecutor` against `anthropic/claude-code-action`
      (map agent model + tools + prompt → a real Claude Code session).
- [ ] Wire verdict artifacts → GitHub PR review comments / checks.
- [ ] Human-gate UX: a PR comment / label that releases the `release` step.
- [ ] Real cost accounting per step (tokens → `budget_usd`).
- [ ] Artifact passing between sessions (plan → diff → verdict) over git refs.

## 🧭 Iteration 3 — Intelligence & resilience

- [ ] Retry/repair loop: a blocked verdict feeds back to the implementer with
      the findings, not just halts.
- [ ] `orchestrator` agent does dynamic routing (pick workflow from issue text).
- [ ] Parallel diffs from backend+frontend merged + conflict-resolved by a step.
- [ ] Learning loop: post-run retro appended to agent prompts over time.
- [ ] Metrics dashboard: pass rates, mean time-to-merge, cost per workflow.

## 🌐 Iteration 4 — Beyond this repo

- [ ] Multi-repo support (agents operating across `apps/web` + `apps/api`
      + future services as separately-gated targets).
- [ ] Custom disciplines on demand (e.g. `data`, `infra`, `docs`, `perf`).
- [ ] Scheduled autonomous maintenance (dependency bumps, flaky-test triage)
      through the `incident`/`bugfix` workflows.

## Principles that don't change

1. Humans gate anything that leaves the repo.
2. Quality gates (review/security/qa) can stop a release; only a human overrides.
3. Least privilege per agent; release is the only pusher.
4. Everything auditable and version-controlled in `.pipeline/`.
