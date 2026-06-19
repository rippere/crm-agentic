"""Loader tests: parse a sample agent + workflow, and reject malformed input."""

from __future__ import annotations

import os

import pytest

from orchestrator.loader import load_agent, load_agents, load_workflow
from orchestrator.models import Gate, Model


def test_load_agents(agents_dir):
    agents = load_agents(agents_dir)
    assert set(agents) == {"architect", "backend", "frontend", "reviewer", "release"}
    architect = agents["architect"]
    assert architect.model is Model.OPUS
    assert architect.model_id == "claude-opus-4-8"
    assert architect.produces == ["plan"]
    assert "## Mission" in architect.body
    assert agents["reviewer"].gate is Gate.BLOCKING


def test_model_id_mapping(agents_dir):
    agents = load_agents(agents_dir)
    assert agents["backend"].model_id == "claude-sonnet-4-6"


def test_load_workflow(workflow_path):
    spec = load_workflow(workflow_path)
    assert spec.name == "sample"
    assert spec.version == 1
    assert spec.trigger.on == ["issue_labeled", "manual"]
    assert spec.defaults.budget_usd == 25
    ids = [s.id for s in spec.steps]
    assert ids == ["plan", "build-backend", "build-frontend", "review", "release"]
    release = spec.step_by_id("release")
    assert release.gate is Gate.HUMAN


def test_missing_frontmatter(tmp_path):
    p = tmp_path / "bad.md"
    p.write_text("no frontmatter here\n", encoding="utf-8")
    with pytest.raises(ValueError, match="missing YAML frontmatter"):
        load_agent(str(p))


def test_unterminated_frontmatter(tmp_path):
    p = tmp_path / "bad.md"
    p.write_text("---\nname: x\n", encoding="utf-8")
    with pytest.raises(ValueError, match="unterminated"):
        load_agent(str(p))


def test_unknown_model(tmp_path):
    p = tmp_path / "bad.md"
    p.write_text("---\nname: bad\nmodel: gpt\n---\nbody\n", encoding="utf-8")
    with pytest.raises(ValueError, match="unknown model"):
        load_agent(str(p))


def test_workflow_missing_name(tmp_path):
    p = tmp_path / "wf.yaml"
    p.write_text("steps:\n  - id: a\n    agent: x\n", encoding="utf-8")
    with pytest.raises(ValueError, match="missing required key 'name'"):
        load_workflow(str(p))


def test_workflow_empty_steps(tmp_path):
    p = tmp_path / "wf.yaml"
    p.write_text("name: x\nsteps: []\n", encoding="utf-8")
    with pytest.raises(ValueError, match="non-empty list"):
        load_workflow(str(p))
