"""Planner tests: deterministic waves + when-based skipping."""

from __future__ import annotations

from orchestrator.loader import load_agents, load_workflow
from orchestrator.planner import plan


def test_waves_structure(agents_dir, workflow_path):
    agents = load_agents(agents_dir)
    spec = load_workflow(workflow_path)
    p = plan(spec, agents, artifacts={})
    # plan -> {build-backend, build-frontend} -> review -> release
    assert p.waves[0] == ["plan"]
    assert set(p.waves[1]) == {"build-backend", "build-frontend"}
    assert p.waves[2] == ["review"]
    assert p.waves[3] == ["release"]


def test_deterministic(agents_dir, workflow_path):
    agents = load_agents(agents_dir)
    spec = load_workflow(workflow_path)
    a = plan(spec, agents, artifacts={})
    b = plan(spec, agents, artifacts={})
    assert a.to_dict() == b.to_dict()


def test_when_skips_step(agents_dir, workflow_path):
    agents = load_agents(agents_dir)
    spec = load_workflow(workflow_path)
    # Only backend is touched -> frontend build is skipped.
    artifacts = {"plan": {"touches": ["backend"]}}
    p = plan(spec, agents, artifacts=artifacts)
    assert p.decisions["build-backend"].decision == "run"
    assert p.decisions["build-frontend"].decision == "skip"
    assert "not in" in p.decisions["build-frontend"].reason


def test_when_unknown_artifact_is_skip(agents_dir, workflow_path):
    agents = load_agents(agents_dir)
    spec = load_workflow(workflow_path)
    # No plan artifact yet -> both conditional builds skip with a reason.
    p = plan(spec, agents, artifacts={})
    assert p.decisions["build-backend"].decision == "skip"
    assert "not available" in p.decisions["build-backend"].reason


def test_gate_resolution(agents_dir, workflow_path):
    agents = load_agents(agents_dir)
    spec = load_workflow(workflow_path)
    p = plan(spec, agents, artifacts={})
    assert p.decisions["review"].gate.value == "blocking"
    assert p.decisions["release"].gate.value == "human"
