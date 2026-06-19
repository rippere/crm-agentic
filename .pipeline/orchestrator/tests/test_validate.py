"""Validator tests: cycle, missing agent, missing producer, bad trigger."""

from __future__ import annotations

from orchestrator.loader import load_agents, load_workflow
from orchestrator.models import (
    Defaults,
    Step,
    Trigger,
    WorkflowSpec,
)
from orchestrator.validate import validate_workflow


def test_valid_workflow(agents_dir, workflow_path):
    agents = load_agents(agents_dir)
    spec = load_workflow(workflow_path)
    assert validate_workflow(spec, agents) == []


def test_missing_agent(agents_dir, workflow_path):
    agents = load_agents(agents_dir)
    spec = load_workflow(workflow_path)
    spec.steps[0].agent = "nonexistent"
    errors = validate_workflow(spec, agents)
    assert any("unknown agent 'nonexistent'" in e for e in errors)


def test_cycle_detection(agents_dir):
    agents = load_agents(agents_dir)
    spec = WorkflowSpec(
        name="cyclic",
        trigger=Trigger(on=["manual"]),
        defaults=Defaults(),
        steps=[
            Step(id="a", agent="backend", depends_on=["b"]),
            Step(id="b", agent="frontend", depends_on=["a"]),
        ],
    )
    errors = validate_workflow(spec, agents)
    assert any("cycle detected" in e for e in errors)


def test_missing_producer_for_consumer(agents_dir):
    agents = load_agents(agents_dir)
    # reviewer consumes 'diff' but nothing upstream produces it.
    spec = WorkflowSpec(
        name="noproducer",
        trigger=Trigger(on=["manual"]),
        defaults=Defaults(),
        steps=[
            Step(id="review", agent="reviewer", produces=["verdict"]),
        ],
    )
    errors = validate_workflow(spec, agents)
    assert any("consumes 'diff'" in e for e in errors)


def test_bad_trigger(agents_dir, workflow_path):
    agents = load_agents(agents_dir)
    spec = load_workflow(workflow_path)
    spec.trigger.on = ["on_push"]
    errors = validate_workflow(spec, agents)
    assert any("trigger.on 'on_push' is not allowed" in e for e in errors)


def test_duplicate_step_id(agents_dir):
    agents = load_agents(agents_dir)
    spec = WorkflowSpec(
        name="dup",
        trigger=Trigger(on=["manual"]),
        defaults=Defaults(),
        steps=[
            Step(id="plan", agent="architect", produces=["plan"]),
            Step(id="plan", agent="architect", produces=["plan"]),
        ],
    )
    errors = validate_workflow(spec, agents)
    assert any("duplicate step id 'plan'" in e for e in errors)


def test_missing_dependency(agents_dir):
    agents = load_agents(agents_dir)
    spec = WorkflowSpec(
        name="missingdep",
        trigger=Trigger(on=["manual"]),
        defaults=Defaults(),
        steps=[Step(id="a", agent="backend", depends_on=["ghost"])],
    )
    errors = validate_workflow(spec, agents)
    assert any("depends_on unknown step 'ghost'" in e for e in errors)
