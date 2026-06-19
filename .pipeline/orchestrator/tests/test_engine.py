"""End-to-end engine tests with the DryRunExecutor."""

from __future__ import annotations

import json
import os

from orchestrator.engine import Runner
from orchestrator.executors import DryRunExecutor, ClaudeCodeExecutor
from orchestrator.models import StepStatus


def _runner(agents_dir, workflows_dir, tmp_path):
    return Runner(
        executor=DryRunExecutor(),
        workflows_dir=workflows_dir,
        agents_dir=agents_dir,
        runs_dir=str(tmp_path / "runs"),
    )


def test_dryrun_end_to_end(agents_dir, workflows_dir, tmp_path):
    runner = _runner(agents_dir, workflows_dir, tmp_path)
    result = runner.run("sample", {"task_brief": "Build a thing"})

    # Run dir exists with run.json.
    assert os.path.isdir(result.run_dir)
    run_json = os.path.join(result.run_dir, "run.json")
    assert os.path.isfile(run_json)
    with open(run_json, encoding="utf-8") as fh:
        manifest = json.load(fh)
    assert manifest["workflow"] == "sample"
    assert manifest["executor"] == "dryrun"
    assert manifest["cost_usd"] == 0.0

    # Artifacts were written.
    assert os.path.isfile(os.path.join(result.run_dir, "plan.json"))
    assert os.path.isfile(os.path.join(result.run_dir, "verdict.json"))
    # Prompt persisted for auditability.
    assert os.path.isfile(os.path.join(result.run_dir, "plan.prompt.txt"))


def test_reaches_human_gate_cleanly(agents_dir, workflows_dir, tmp_path):
    runner = _runner(agents_dir, workflows_dir, tmp_path)
    result = runner.run("sample", {"task_brief": "Build a thing"})
    m = result.manifest

    # The run pauses at the human-gated release step.
    assert m.status == "needs_human"
    release = m.step_state("release")
    assert release.status is StepStatus.PENDING
    assert release.needs_human is True

    # Steps before it ran.
    assert m.step_state("plan").status is StepStatus.PASSED
    assert m.step_state("review").status is StepStatus.PASSED
    # The dryrun plan touches both, so both builds run.
    assert m.step_state("build-backend").status is StepStatus.PASSED
    assert m.step_state("build-frontend").status is StepStatus.PASSED


def test_claude_code_executor_is_stub():
    ex = ClaudeCodeExecutor()
    import pytest

    from orchestrator.models import Step

    step = Step(id="build", agent="backend")
    with pytest.raises(NotImplementedError, match="claude-code-action"):
        ex.run_step(step, _FakeAgent(), "/tmp", {})


class _FakeAgent:
    name = "backend"
    model_id = "claude-sonnet-4-6"
    body = ""
    gate = None
