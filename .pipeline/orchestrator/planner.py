"""Pure execution planner (ARCHITECTURE §5, §7, §8 rule 6).

``plan(spec, agents, artifacts={})`` topologically sorts the workflow's steps
respecting ``depends_on``, evaluates each step's ``when`` against the currently
known artifacts to decide runnable vs skipped, and groups the steps into
ordered parallel **waves** (a wave = steps whose dependencies are all already
resolved).

The planner is **pure**: it performs no I/O and never mutates its inputs, so
the same (spec, agents, artifacts) always yields the same plan.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

from . import whenexpr
from .models import AgentDef, Gate, Step, WorkflowSpec


@dataclass
class StepDecision:
    """The planner's verdict for one step."""

    step_id: str
    agent: str
    decision: str  # "run" | "skip"
    reason: str
    gate: Gate
    depends_on: list[str] = field(default_factory=list)


@dataclass
class ExecutionPlan:
    """An ordered list of waves plus per-step decisions."""

    workflow: str
    waves: list[list[str]] = field(default_factory=list)
    decisions: dict[str, StepDecision] = field(default_factory=dict)

    @property
    def ordered_step_ids(self) -> list[str]:
        return [sid for wave in self.waves for sid in wave]

    def to_dict(self) -> dict:
        return {
            "workflow": self.workflow,
            "waves": [list(w) for w in self.waves],
            "decisions": {
                sid: {
                    "agent": d.agent,
                    "decision": d.decision,
                    "reason": d.reason,
                    "gate": d.gate.value,
                    "depends_on": list(d.depends_on),
                }
                for sid, d in self.decisions.items()
            },
        }


def _effective_gate(step: Step, agents: Mapping[str, AgentDef]) -> Gate:
    if step.gate is not None:
        return step.gate
    agent = agents.get(step.agent)
    return agent.gate if agent is not None else Gate.NONE


def _topo_waves(spec: WorkflowSpec) -> list[list[str]]:
    """Kahn-style layering into deterministic waves.

    Each wave contains the steps whose dependencies are all in earlier waves.
    Within a wave, step ids are kept in their declaration order for determinism.
    """
    order = [s.id for s in spec.steps]  # declaration order (stable)
    deps: dict[str, set[str]] = {
        s.id: {d for d in s.depends_on if d in order} for s in spec.steps
    }
    resolved: set[str] = set()
    waves: list[list[str]] = []
    remaining = list(order)

    while remaining:
        wave = [sid for sid in remaining if deps[sid] <= resolved]
        if not wave:
            # Should not happen on a validated (acyclic) spec; guard anyway.
            raise ValueError(
                "cannot build waves: unresolved dependencies "
                f"(possible cycle) among {remaining}"
            )
        waves.append(wave)
        resolved.update(wave)
        remaining = [sid for sid in remaining if sid not in resolved]
    return waves


def plan(
    spec: WorkflowSpec,
    agents: Mapping[str, AgentDef],
    artifacts: Mapping[str, dict] | None = None,
) -> ExecutionPlan:
    """Build a deterministic :class:`ExecutionPlan` (no side effects)."""
    artifacts = dict(artifacts or {})

    waves = _topo_waves(spec)
    decisions: dict[str, StepDecision] = {}

    for step in spec.steps:
        gate = _effective_gate(step, agents)
        if step.when is None:
            decision, reason = "run", "no condition"
        else:
            try:
                result, reason = whenexpr.evaluate(step.when, artifacts)
            except whenexpr.WhenSyntaxError as exc:
                # A validated spec won't hit this; record as skip for safety.
                result, reason = False, f"invalid when expression: {exc}"
            decision = "run" if result else "skip"
        decisions[step.id] = StepDecision(
            step_id=step.id,
            agent=step.agent,
            decision=decision,
            reason=reason,
            gate=gate,
            depends_on=list(step.depends_on),
        )

    return ExecutionPlan(workflow=spec.name, waves=waves, decisions=decisions)
