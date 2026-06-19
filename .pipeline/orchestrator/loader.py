"""Parsers for agent markdown files and workflow YAML specs.

``load_agents(dir)``   -> {name: AgentDef}  (ARCHITECTURE §3)
``load_agent(path)``   -> AgentDef
``load_workflow(path)`` -> WorkflowSpec      (ARCHITECTURE §5)

All malformed input raises ``ValueError`` naming the offending file and the
reason.
"""

from __future__ import annotations

import os
from typing import Any

import yaml

from .models import (
    AgentDef,
    Defaults,
    Gate,
    InputSpec,
    Model,
    Step,
    Trigger,
    WorkflowSpec,
)


def _split_frontmatter(text: str, path: str) -> tuple[dict[str, Any], str]:
    """Split a markdown file into (frontmatter dict, body).

    Frontmatter is the YAML block delimited by lines containing only ``---``.
    The file must begin with such a delimiter.
    """
    lines = text.splitlines()
    # Tolerate a leading BOM / blank lines before the opening delimiter.
    start = 0
    while start < len(lines) and lines[start].strip() == "":
        start += 1
    if start >= len(lines) or lines[start].strip() != "---":
        raise ValueError(
            f"{path}: missing YAML frontmatter; file must start with a '---' line"
        )

    closing = None
    for idx in range(start + 1, len(lines)):
        if lines[idx].strip() == "---":
            closing = idx
            break
    if closing is None:
        raise ValueError(f"{path}: unterminated YAML frontmatter (no closing '---')")

    fm_text = "\n".join(lines[start + 1 : closing])
    body = "\n".join(lines[closing + 1 :]).strip("\n")

    try:
        data = yaml.safe_load(fm_text) or {}
    except yaml.YAMLError as exc:
        raise ValueError(f"{path}: invalid YAML frontmatter: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"{path}: frontmatter must be a YAML mapping")
    return data, body


def _as_str_list(value: Any, path: str, field_name: str) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(v) for v in value]
    raise ValueError(f"{path}: '{field_name}' must be a list, got {type(value).__name__}")


def load_agent(path: str) -> AgentDef:
    """Parse a single ``agents/<name>.md`` file into an :class:`AgentDef`."""
    try:
        with open(path, "r", encoding="utf-8") as fh:
            text = fh.read()
    except OSError as exc:
        raise ValueError(f"{path}: cannot read agent file: {exc}") from exc

    fm, body = _split_frontmatter(text, path)

    if "name" not in fm:
        raise ValueError(f"{path}: agent frontmatter missing required key 'name'")
    if "model" not in fm:
        raise ValueError(f"{path}: agent frontmatter missing required key 'model'")

    try:
        model = Model.parse(fm["model"])
    except ValueError as exc:
        raise ValueError(f"{path}: {exc}") from exc

    try:
        gate = Gate.parse(fm.get("gate"))
    except ValueError as exc:
        raise ValueError(f"{path}: {exc}") from exc

    max_turns = fm.get("max_turns", 40)
    try:
        max_turns = int(max_turns)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{path}: 'max_turns' must be an integer") from exc

    return AgentDef(
        name=str(fm["name"]),
        discipline=str(fm.get("discipline", "")),
        model=model,
        tools=_as_str_list(fm.get("tools"), path, "tools"),
        produces=_as_str_list(fm.get("produces"), path, "produces"),
        consumes=_as_str_list(fm.get("consumes"), path, "consumes"),
        gate=gate,
        escalates_to=(str(fm["escalates_to"]) if fm.get("escalates_to") else None),
        max_turns=max_turns,
        body=body,
    )


def load_agents(directory: str) -> dict[str, AgentDef]:
    """Load every ``*.md`` agent definition under ``directory``.

    Returns a mapping of agent name -> :class:`AgentDef`. Raises ``ValueError``
    on a malformed file or a name/filename mismatch / duplicate name.
    """
    if not os.path.isdir(directory):
        raise ValueError(f"{directory}: agents directory does not exist")

    agents: dict[str, AgentDef] = {}
    for fname in sorted(os.listdir(directory)):
        if not fname.endswith(".md") or fname.upper() == "README.MD":
            continue
        path = os.path.join(directory, fname)
        agent = load_agent(path)
        stem = os.path.splitext(fname)[0]
        if agent.name != stem:
            raise ValueError(
                f"{path}: agent name '{agent.name}' must match filename '{stem}'"
            )
        if agent.name in agents:
            raise ValueError(f"{path}: duplicate agent name '{agent.name}'")
        agents[agent.name] = agent
    return agents


def _parse_trigger(data: Any, path: str) -> Trigger:
    if data is None:
        return Trigger()
    if not isinstance(data, dict):
        raise ValueError(f"{path}: 'trigger' must be a mapping")
    # YAML 1.1 parses the bare key `on:` as the boolean True; PyYAML's
    # safe_load follows this. Accept either spelling so workflow authors can
    # write the natural `on:` form.
    on_value = data.get("on")
    if on_value is None and True in data:
        on_value = data[True]
    return Trigger(
        on=_as_str_list(on_value, path, "trigger.on"),
        labels=_as_str_list(data.get("labels"), path, "trigger.labels"),
        cron=(str(data["cron"]) if data.get("cron") else None),
    )


def _parse_inputs(data: Any, path: str) -> list[InputSpec]:
    if data is None:
        return []
    if not isinstance(data, list):
        raise ValueError(f"{path}: 'inputs' must be a list")
    inputs: list[InputSpec] = []
    for raw in data:
        if not isinstance(raw, dict) or "name" not in raw:
            raise ValueError(f"{path}: each input must be a mapping with a 'name'")
        inputs.append(
            InputSpec(
                name=str(raw["name"]),
                required=bool(raw.get("required", False)),
                description=str(raw.get("description", "")),
            )
        )
    return inputs


def _parse_defaults(data: Any, path: str) -> Defaults:
    if data is None:
        return Defaults()
    if not isinstance(data, dict):
        raise ValueError(f"{path}: 'defaults' must be a mapping")
    defaults = Defaults()
    if "max_retries" in data:
        try:
            defaults.max_retries = int(data["max_retries"])
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{path}: 'defaults.max_retries' must be an integer") from exc
    if "budget_usd" in data:
        try:
            defaults.budget_usd = float(data["budget_usd"])
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{path}: 'defaults.budget_usd' must be a number") from exc
    return defaults


def _parse_steps(data: Any, path: str) -> list[Step]:
    if not isinstance(data, list) or not data:
        raise ValueError(f"{path}: 'steps' must be a non-empty list")
    steps: list[Step] = []
    for raw in data:
        if not isinstance(raw, dict):
            raise ValueError(f"{path}: each step must be a mapping")
        if "id" not in raw:
            raise ValueError(f"{path}: a step is missing required key 'id'")
        if "agent" not in raw:
            raise ValueError(f"{path}: step '{raw['id']}' missing required key 'agent'")
        gate_raw = raw.get("gate")
        try:
            gate = Gate.parse(gate_raw) if gate_raw is not None else None
        except ValueError as exc:
            raise ValueError(f"{path}: step '{raw['id']}': {exc}") from exc
        steps.append(
            Step(
                id=str(raw["id"]),
                agent=str(raw["agent"]),
                depends_on=_as_str_list(raw.get("depends_on"), path, "depends_on"),
                when=(str(raw["when"]) if raw.get("when") is not None else None),
                produces=_as_str_list(raw.get("produces"), path, "produces"),
                consumes=_as_str_list(raw.get("consumes"), path, "consumes"),
                gate=gate,
            )
        )
    return steps


def load_workflow(path: str) -> WorkflowSpec:
    """Parse a ``workflows/<name>.yaml`` file into a :class:`WorkflowSpec`."""
    try:
        with open(path, "r", encoding="utf-8") as fh:
            text = fh.read()
    except OSError as exc:
        raise ValueError(f"{path}: cannot read workflow file: {exc}") from exc

    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ValueError(f"{path}: invalid YAML: {exc}") from exc

    if not isinstance(data, dict):
        raise ValueError(f"{path}: workflow must be a YAML mapping")
    if "name" not in data:
        raise ValueError(f"{path}: workflow missing required key 'name'")

    version = data.get("version", 1)
    try:
        version = int(version)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{path}: 'version' must be an integer") from exc

    return WorkflowSpec(
        name=str(data["name"]),
        description=str(data.get("description", "")),
        version=version,
        trigger=_parse_trigger(data.get("trigger"), path),
        inputs=_parse_inputs(data.get("inputs"), path),
        defaults=_parse_defaults(data.get("defaults"), path),
        steps=_parse_steps(data.get("steps"), path),
    )
