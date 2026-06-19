"""The Runner: load -> validate -> plan -> execute (ARCHITECTURE §1, §4, §6, §8).

``Runner`` ties the package together:

  1. Loads agents + the named workflow.
  2. Validates (aborts with errors if invalid).
  3. Creates ``.pipeline/runs/<run_id>/`` (run_id = workflow + UTC timestamp),
     writes ``run.json``.
  4. Executes waves in order via the chosen :class:`Executor`, evaluating each
     step's ``when`` against artifacts known so far.
  5. Honors gates:
       - ``blocking`` non-pass halts the run after ``defaults.max_retries``.
       - ``human`` pauses cleanly: the step is left ``pending`` with a
         needs_human note and the run stops (status ``needs_human``).
  6. Persists artifacts and an updated ``run.json`` after every step.

Cost/budget is tracked on the manifest; DryRun spends $0.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

from . import paths
from .executors import Executor
from .loader import load_agents, load_workflow
from .models import (
    AgentDef,
    Gate,
    RunManifest,
    StepState,
    StepStatus,
    WorkflowSpec,
)
from .planner import plan as build_plan
from .validate import validate_workflow
from . import whenexpr


class ValidationError(Exception):
    """Raised when a workflow fails validation; carries the error list."""

    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("workflow validation failed:\n  - " + "\n  - ".join(errors))


@dataclass
class RunResult:
    manifest: RunManifest
    run_dir: str


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Runner:
    """Loads, validates, plans and executes a workflow."""

    def __init__(
        self,
        executor: Executor,
        workflows_dir: Optional[str] = None,
        agents_dir: Optional[str] = None,
        runs_dir: Optional[str] = None,
    ):
        self.executor = executor
        self.workflows_dir = workflows_dir or paths.workflows_dir()
        self.agents_dir = agents_dir or paths.agents_dir()
        self.runs_dir = runs_dir or paths.runs_dir()

    # -- loading + validation ---------------------------------------------

    def load(self, workflow_name: str) -> tuple[WorkflowSpec, dict[str, AgentDef]]:
        agents = load_agents(self.agents_dir)
        wf_path = paths.workflow_path(self.workflows_dir, workflow_name)
        spec = load_workflow(wf_path)
        return spec, agents

    def validate(self, workflow_name: str) -> tuple[WorkflowSpec, dict[str, AgentDef]]:
        spec, agents = self.load(workflow_name)
        errors = validate_workflow(spec, agents)
        if errors:
            raise ValidationError(errors)
        return spec, agents

    # -- execution ---------------------------------------------------------

    def run(self, workflow_name: str, inputs: dict[str, Any]) -> RunResult:
        spec, agents = self.validate(workflow_name)

        now = _utcnow()
        run_id = f"{spec.name}-{now.strftime('%Y%m%dT%H%M%SZ')}"
        run_dir = os.path.join(self.runs_dir, run_id)
        os.makedirs(run_dir, exist_ok=True)

        # Seed artifacts: the trigger provides task_brief if supplied.
        artifacts: dict[str, dict] = {}
        for key, value in inputs.items():
            artifacts[key] = self._wrap_input(value)

        manifest = RunManifest(
            run_id=run_id,
            workflow=spec.name,
            status="running",
            inputs=dict(inputs),
            created_at=_iso(now),
            updated_at=_iso(now),
            budget_usd=spec.defaults.budget_usd,
            cost_usd=0.0,
            executor=self.executor.name,
        )
        # Pre-populate step states from the (initial) plan so run.json shows the DAG.
        initial = build_plan(spec, agents, artifacts)
        for step in spec.steps:
            decision = initial.decisions[step.id]
            manifest.steps.append(
                StepState(
                    id=step.id,
                    agent=step.agent,
                    status=StepStatus.PENDING,
                    gate=decision.gate,
                    reason=decision.reason,
                )
            )
        self._persist(manifest, run_dir)

        halted = False
        for wave in initial.waves:
            if halted:
                break
            for step_id in wave:
                step = spec.step_by_id(step_id)
                assert step is not None
                agent = agents[step.agent]
                state = manifest.step_state(step_id)
                assert state is not None

                # Re-evaluate `when` against artifacts known so far (live).
                if step.when is not None:
                    result, reason = whenexpr.evaluate(step.when, artifacts)
                    if not result:
                        state.status = StepStatus.SKIPPED
                        state.reason = f"when false: {reason}"
                        self._persist(manifest, run_dir)
                        continue

                # If any dependency was blocked/failed, skip dependents.
                if self._dep_unsatisfied(step, manifest):
                    state.status = StepStatus.SKIPPED
                    state.reason = "upstream dependency did not pass"
                    self._persist(manifest, run_dir)
                    continue

                effective_gate = step.gate if step.gate is not None else agent.gate

                # Human gate: pause cleanly before the step's effects land.
                if effective_gate is Gate.HUMAN:
                    state.status = StepStatus.PENDING
                    state.needs_human = True
                    state.reason = "human gate: awaiting human decision"
                    manifest.notes.append(
                        f"step '{step_id}' requires a human decision (gate: human)"
                    )
                    manifest.status = "needs_human"
                    self._persist(manifest, run_dir)
                    halted = True
                    break

                # Execute, with retries for blocking gates.
                final_state = self._execute_with_retries(
                    step, agent, run_dir, artifacts, spec.defaults.max_retries
                )
                # Carry over the pre-planned gate/reason fields onto the state.
                manifest.steps[manifest.steps.index(state)] = final_state
                manifest.cost_usd += final_state.cost_usd

                # Register produced artifacts for downstream steps.
                self._register_artifacts(final_state, run_dir, artifacts)

                # Budget guardrail (§8 rule 2).
                if manifest.budget_usd and manifest.cost_usd > manifest.budget_usd:
                    manifest.notes.append(
                        f"budget exceeded: ${manifest.cost_usd:.2f} > "
                        f"${manifest.budget_usd:.2f}; escalating to human"
                    )
                    manifest.status = "needs_human"
                    self._persist(manifest, run_dir)
                    halted = True
                    break

                # Gate enforcement (§4).
                if self._is_blocking_failure(final_state, effective_gate):
                    final_state.status = StepStatus.BLOCKED
                    manifest.status = "blocked"
                    manifest.notes.append(
                        f"step '{step_id}' blocked the run (gate: blocking, "
                        f"verdict: {final_state.verdict})"
                    )
                    self._persist(manifest, run_dir)
                    halted = True
                    break

                self._persist(manifest, run_dir)

        if not halted and manifest.status == "running":
            manifest.status = "passed"
            self._persist(manifest, run_dir)

        return RunResult(manifest=manifest, run_dir=run_dir)

    # -- helpers -----------------------------------------------------------

    def _execute_with_retries(
        self,
        step,
        agent: AgentDef,
        run_dir: str,
        artifacts: dict,
        max_retries: int,
    ) -> StepState:
        attempts = 0
        last: StepState
        while True:
            attempts += 1
            last = self.executor.run_step(step, agent, run_dir, artifacts)
            last.attempts = attempts
            failed = last.status in (StepStatus.FAILED, StepStatus.BLOCKED) or (
                last.verdict is not None and last.verdict != "pass"
            )
            if not failed or attempts > max_retries:
                break
        return last

    @staticmethod
    def _is_blocking_failure(state: StepState, gate: Gate) -> bool:
        if gate is not Gate.BLOCKING:
            return False
        if state.status in (StepStatus.FAILED, StepStatus.BLOCKED):
            return True
        if state.verdict is not None and state.verdict != "pass":
            return True
        return False

    @staticmethod
    def _dep_unsatisfied(step, manifest: RunManifest) -> bool:
        for dep in step.depends_on:
            dep_state = manifest.step_state(dep)
            if dep_state is None:
                continue
            # A skipped dep is "satisfied-but-empty" (§7); only hard failures count.
            if dep_state.status in (StepStatus.BLOCKED, StepStatus.FAILED):
                return True
        return False

    def _register_artifacts(
        self, state: StepState, run_dir: str, artifacts: dict
    ) -> None:
        for kind in state.produced:
            json_path = os.path.join(run_dir, f"{kind}.json")
            if os.path.exists(json_path):
                try:
                    with open(json_path, "r", encoding="utf-8") as fh:
                        payload = json.load(fh)
                except (OSError, json.JSONDecodeError):
                    payload = {"kind": kind}
            else:
                payload = {"kind": kind}
            if not isinstance(payload, dict):
                payload = {"value": payload}
            artifacts[kind] = payload

    @staticmethod
    def _wrap_input(value: Any) -> dict:
        if isinstance(value, dict):
            return value
        return {"value": value, "text": str(value)}

    def _persist(self, manifest: RunManifest, run_dir: str) -> None:
        manifest.updated_at = _iso(_utcnow())
        path = os.path.join(run_dir, "run.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(manifest.to_dict(), fh, indent=2, sort_keys=False)


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
