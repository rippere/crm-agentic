"""Executors decide *how* a step's agent actually runs (ARCHITECTURE §1, §9).

The orchestrator produces a substrate-agnostic plan; an :class:`Executor` is
the side-effecting layer that turns one planned step into a :class:`StepState`.

  - :class:`DryRunExecutor` — fully working, offline. Resolves the prompt
    (agent body + inputs), writes a stub artifact for each ``produces``, marks
    the step ``passed`` (gated steps get a synthetic ``pass`` verdict), and
    spends $0. Used in CI to validate every workflow on every push.
  - :class:`ClaudeCodeExecutor` — a documented STUB describing how a step maps
    to a Claude Code / Anthropic invocation. It does not make API calls; it
    raises ``NotImplementedError`` pointing at the GitHub Actions integration.
"""

from __future__ import annotations

import json
import os
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, Mapping

from .models import AgentDef, Gate, Step, StepState, StepStatus


def _utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def resolve_prompt(agent: AgentDef, artifacts: Mapping[str, Any]) -> str:
    """Compose the prompt for a step: agent system prompt + available inputs.

    This is the same prompt a real Claude Code invocation would receive as its
    system/context. Kept deterministic so DryRun output is reproducible.
    """
    lines = [agent.body.strip(), "", "## Available inputs"]
    if not artifacts:
        lines.append("(none)")
    else:
        for name in sorted(artifacts):
            value = artifacts[name]
            try:
                rendered = json.dumps(value, sort_keys=True, default=str)
            except (TypeError, ValueError):
                rendered = str(value)
            lines.append(f"- {name}: {rendered}")
    return "\n".join(lines)


class Executor(ABC):
    """Abstract base for step executors."""

    name: str = "executor"

    @abstractmethod
    def run_step(
        self,
        step: Step,
        agent: AgentDef,
        run_dir: str,
        artifacts: Mapping[str, Any],
    ) -> StepState:
        """Execute one step and return its resulting :class:`StepState`.

        Implementations should write any produced artifacts into ``run_dir``
        and update the returned state's ``produced`` list accordingly.
        """
        raise NotImplementedError


class DryRunExecutor(Executor):
    """Offline executor: records prompts, writes stub artifacts, spends $0."""

    name = "dryrun"

    def run_step(
        self,
        step: Step,
        agent: AgentDef,
        run_dir: str,
        artifacts: Mapping[str, Any],
    ) -> StepState:
        effective_gate = step.gate if step.gate is not None else agent.gate
        state = StepState(
            id=step.id,
            agent=step.agent,
            status=StepStatus.RUNNING,
            gate=effective_gate,
            started_at=_utcnow(),
            attempts=1,
            cost_usd=0.0,
        )

        prompt = resolve_prompt(agent, artifacts)

        # Persist the resolved prompt for auditability (§8 rule 5).
        prompt_path = os.path.join(run_dir, f"{step.id}.prompt.txt")
        with open(prompt_path, "w", encoding="utf-8") as fh:
            fh.write(prompt)

        # Write a stub artifact for each declared `produces`.
        produced: list[str] = []
        for kind in step.produces:
            artifact = self._stub_artifact(step, agent, kind)
            self._write_artifact(run_dir, kind, artifact)
            produced.append(kind)

        # Gated steps get a synthetic passing verdict so the run can proceed.
        if effective_gate in (Gate.BLOCKING, Gate.ADVISORY):
            state.verdict = "pass"

        state.produced = produced
        state.status = StepStatus.PASSED
        state.ended_at = _utcnow()
        state.reason = f"dryrun: produced {produced or '[]'}"
        return state

    @staticmethod
    def _stub_artifact(step: Step, agent: AgentDef, kind: str) -> Any:
        """Produce a deterministic stub payload for an artifact kind."""
        if kind == "verdict":
            return {"status": "pass", "findings": [], "by": agent.name}
        if kind == "plan":
            # Provide a `touches` field so downstream `when` conditions resolve.
            return {
                "summary": f"[dryrun plan from {agent.name} for step {step.id}]",
                "touches": ["backend", "frontend"],
            }
        if kind == "diff":
            return {"files": [], "summary": f"[dryrun diff from {agent.name}]"}
        if kind == "release_note":
            return {"markdown": f"[dryrun release note from {agent.name}]"}
        return {"kind": kind, "by": agent.name, "dryrun": True}

    @staticmethod
    def _write_artifact(run_dir: str, kind: str, payload: Any) -> None:
        # Markdown-ish artifacts get a .md mirror; everything gets JSON.
        json_path = os.path.join(run_dir, f"{kind}.json")
        with open(json_path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, sort_keys=True, default=str)


class ClaudeCodeExecutor(Executor):
    """STUB executor mapping a step to a Claude Code / Anthropic invocation.

    Interface (what a real implementation would do per ARCHITECTURE §9):

      1. Resolve the prompt via :func:`resolve_prompt` (agent body + inputs).
      2. Select the concrete model id from ``agent.model.model_id``
         (opus -> claude-opus-4-8, sonnet -> claude-sonnet-4-6,
          haiku -> claude-haiku-4-5-20251001).
      3. Pass ``agent.tools`` as the tool allowlist (least privilege, §8 rule 4).
      4. Invoke ``anthropic/claude-code-action`` (in GitHub Actions) or the
         Anthropic SDK (standalone) with ANTHROPIC_API_KEY, capped by
         ``agent.max_turns`` and the run's ``budget_usd``.
      5. Parse the agent's output into the declared ``produces`` artifacts and,
         for gated steps, a ``{status: pass|block|warn, findings: [...]}``
         verdict; write them to ``run_dir``; track real token cost.

    This stub intentionally raises rather than making network calls. The live
    integration lives in ``.github/workflows/agentic-pipeline.yml``.
    """

    name = "claude-code"

    def run_step(
        self,
        step: Step,
        agent: AgentDef,
        run_dir: str,
        artifacts: Mapping[str, Any],
    ) -> StepState:
        raise NotImplementedError(
            "ClaudeCodeExecutor is a stub. Real agent dispatch runs via "
            "anthropic/claude-code-action in .github/workflows/agentic-pipeline.yml "
            f"(step '{step.id}', agent '{agent.name}', model '{agent.model_id}'). "
            "Use --executor dryrun for offline runs."
        )


def get_executor(name: str) -> Executor:
    """Factory mapping a CLI name to an executor instance."""
    table: dict[str, type[Executor]] = {
        "dryrun": DryRunExecutor,
        "claude-code": ClaudeCodeExecutor,
    }
    key = name.strip().lower()
    if key not in table:
        raise ValueError(
            f"unknown executor '{name}'; expected one of {sorted(table)}"
        )
    return table[key]()
