"""Shared fixtures: small, self-contained agent + workflow files.

These fixtures are deliberately independent of the real ``agents/*.md`` and
``workflows/*.yaml`` (which other authors own) so the suite is deterministic.
"""

from __future__ import annotations

import os
import textwrap

import pytest

# Make ``orchestrator`` importable when pytest is invoked from .pipeline/.
import sys

_PIPELINE_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _PIPELINE_ROOT not in sys.path:
    sys.path.insert(0, _PIPELINE_ROOT)


REQUIRED_SECTIONS = [
    "Mission",
    "Responsibilities",
    "Operating procedure",
    "Inputs",
    "Outputs",
    "Handoff",
    "Guardrails",
    "Definition of done",
]


def _agent_body() -> str:
    return "\n\n".join(f"## {s}\n\nLorem ipsum." for s in REQUIRED_SECTIONS)


def write_agent(
    directory: str,
    name: str,
    *,
    model: str = "sonnet",
    tools=("Read", "Write"),
    produces=(),
    consumes=(),
    gate: str = "none",
    body: str | None = None,
) -> str:
    tools_yaml = "[" + ", ".join(tools) + "]"
    produces_yaml = "[" + ", ".join(produces) + "]"
    consumes_yaml = "[" + ", ".join(consumes) + "]"
    fm = textwrap.dedent(
        f"""\
        ---
        name: {name}
        discipline: {name.title()} discipline
        model: {model}
        tools: {tools_yaml}
        produces: {produces_yaml}
        consumes: {consumes_yaml}
        gate: {gate}
        escalates_to: orchestrator
        max_turns: 40
        ---
        """
    )
    content = fm + "\n" + (body if body is not None else _agent_body()) + "\n"
    path = os.path.join(directory, f"{name}.md")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(content)
    return path


SAMPLE_WORKFLOW = textwrap.dedent(
    """\
    name: sample
    description: A sample plan->build->review->release workflow.
    version: 1

    trigger:
      on: [issue_labeled, manual]
      labels: [agent:sample]

    inputs:
      - name: task_brief
        required: true
        description: What to build.

    defaults:
      max_retries: 1
      budget_usd: 25

    steps:
      - id: plan
        agent: architect
        produces: [plan]

      - id: build-backend
        agent: backend
        depends_on: [plan]
        when: "backend in plan.touches"
        consumes: [plan]
        produces: [diff]

      - id: build-frontend
        agent: frontend
        depends_on: [plan]
        when: "frontend in plan.touches"
        consumes: [plan]
        produces: [diff]

      - id: review
        agent: reviewer
        depends_on: [build-backend, build-frontend]
        produces: [verdict]
        gate: blocking

      - id: release
        agent: release
        depends_on: [review]
        produces: [release_note]
        gate: human
    """
)


@pytest.fixture
def agents_dir(tmp_path) -> str:
    d = tmp_path / "agents"
    d.mkdir()
    sd = str(d)
    write_agent(sd, "architect", model="opus", produces=["plan"], consumes=["task_brief"])
    write_agent(sd, "backend", model="sonnet", produces=["diff"], consumes=["plan"])
    write_agent(sd, "frontend", model="sonnet", produces=["diff"], consumes=["plan"])
    write_agent(sd, "reviewer", model="opus", produces=["verdict"],
                consumes=["diff"], gate="blocking")
    write_agent(sd, "release", model="sonnet", produces=["release_note"], gate="human")
    return sd


@pytest.fixture
def workflows_dir(tmp_path) -> str:
    d = tmp_path / "workflows"
    d.mkdir()
    path = d / "sample.yaml"
    path.write_text(SAMPLE_WORKFLOW, encoding="utf-8")
    return str(d)


@pytest.fixture
def workflow_path(workflows_dir) -> str:
    return os.path.join(workflows_dir, "sample.yaml")
