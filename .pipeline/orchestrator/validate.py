"""Static validation of agents and workflows (ARCHITECTURE §3, §5).

``validate_workflow(spec, agents)`` returns a list of human-readable error
strings; an empty list means the spec is valid. It enforces:

  - step ids are unique
  - every ``agent`` reference resolves to a known agent
  - every ``depends_on`` id exists
  - the dependency graph is acyclic (cycle detection)
  - a step that consumes an artifact has a transitive ancestor producing it
  - ``trigger.on`` values are within the allowed set
  - each referenced agent has the required frontmatter + body H2 sections

``validate_agent(agent)`` checks a single agent definition.
"""

from __future__ import annotations

from typing import Mapping

from . import whenexpr
from .models import AgentDef, WorkflowSpec

ALLOWED_TRIGGERS = {"issue_labeled", "pull_request", "manual", "schedule"}

REQUIRED_BODY_SECTIONS = [
    "Mission",
    "Responsibilities",
    "Operating procedure",
    "Inputs",
    "Outputs",
    "Handoff",
    "Guardrails",
    "Definition of done",
]


def validate_agent(agent: AgentDef) -> list[str]:
    """Validate one agent definition's frontmatter + required body sections."""
    errors: list[str] = []
    if not agent.name:
        errors.append("agent: missing 'name'")
    if not agent.discipline:
        errors.append(f"agent '{agent.name}': missing 'discipline'")

    # Required H2 sections in the body. Match lines like '## Mission'.
    body_lines = [ln.strip() for ln in agent.body.splitlines()]
    present = {
        ln[3:].strip().lower()
        for ln in body_lines
        if ln.startswith("## ")
    }
    for section in REQUIRED_BODY_SECTIONS:
        if section.lower() not in present:
            errors.append(
                f"agent '{agent.name}': missing required body section '## {section}'"
            )
    return errors


def _detect_cycle(adjacency: Mapping[str, list[str]]) -> list[str]:
    """Return a list with one error per detected cycle (empty if acyclic)."""
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {node: WHITE for node in adjacency}
    errors: list[str] = []

    def visit(node: str, stack: list[str]) -> None:
        color[node] = GRAY
        stack.append(node)
        for dep in adjacency.get(node, []):
            if dep not in color:
                continue  # missing dep reported elsewhere
            if color[dep] == GRAY:
                cycle = stack[stack.index(dep):] + [dep]
                errors.append("cycle detected: " + " -> ".join(cycle))
            elif color[dep] == WHITE:
                visit(dep, stack)
        stack.pop()
        color[node] = BLACK

    for node in adjacency:
        if color[node] == WHITE:
            visit(node, [])
    # De-duplicate (a cycle may be discovered from multiple entry points).
    seen: set[frozenset[str]] = set()
    unique: list[str] = []
    for err in errors:
        key = frozenset(err.replace("cycle detected: ", "").split(" -> "))
        if key not in seen:
            seen.add(key)
            unique.append(err)
    return unique


def _ancestors(step_id: str, adjacency: Mapping[str, list[str]]) -> set[str]:
    """All transitive dependencies of ``step_id`` (excluding itself)."""
    seen: set[str] = set()
    stack = list(adjacency.get(step_id, []))
    while stack:
        node = stack.pop()
        if node in seen or node not in adjacency:
            continue
        seen.add(node)
        stack.extend(adjacency.get(node, []))
    return seen


def validate_workflow(
    spec: WorkflowSpec, agents: Mapping[str, AgentDef]
) -> list[str]:
    """Validate a workflow against the agent roster. Empty list == valid."""
    errors: list[str] = []

    # --- step ids unique --------------------------------------------------
    seen_ids: set[str] = set()
    duplicate_ids: set[str] = set()
    for step in spec.steps:
        if step.id in seen_ids:
            duplicate_ids.add(step.id)
        seen_ids.add(step.id)
    for dup in sorted(duplicate_ids):
        errors.append(f"duplicate step id '{dup}'")

    # --- trigger.on values ------------------------------------------------
    for trig in spec.trigger.on:
        if trig not in ALLOWED_TRIGGERS:
            errors.append(
                f"trigger.on '{trig}' is not allowed; "
                f"expected one of {sorted(ALLOWED_TRIGGERS)}"
            )

    # --- agent references resolve + agent defs valid ----------------------
    referenced_agents: set[str] = set()
    for step in spec.steps:
        if step.agent not in agents:
            errors.append(
                f"step '{step.id}': unknown agent '{step.agent}'"
            )
        else:
            referenced_agents.add(step.agent)
    for agent_name in sorted(referenced_agents):
        errors.extend(validate_agent(agents[agent_name]))

    # --- depends_on ids exist + build adjacency ---------------------------
    adjacency: dict[str, list[str]] = {step.id: [] for step in spec.steps}
    for step in spec.steps:
        for dep in step.depends_on:
            if dep not in seen_ids:
                errors.append(
                    f"step '{step.id}': depends_on unknown step '{dep}'"
                )
            else:
                adjacency[step.id].append(dep)

    # --- acyclic ----------------------------------------------------------
    errors.extend(_detect_cycle(adjacency))

    # --- consumer/producer reachability -----------------------------------
    # A step that consumes an artifact must have a transitive ancestor that
    # produces it. The set of consumed kinds comes from the step itself and
    # from the agent's declared `consumes`. If the graph has a cycle we skip
    # this check (ancestor sets are undefined).
    if not any(e.startswith("cycle detected") for e in errors):
        # Artifacts available at the start of the run (no producer step needed):
        #   - `task_brief` is always seeded by the trigger (§6).
        #   - any declared workflow input name.
        #   - a `pull_request` trigger seeds the existing `diff` from the PR;
        #     a review-only workflow (e.g. pr-review) consumes it without a
        #     build step producing it.
        seeded: set[str] = {"task_brief"}
        seeded.update(inp.name for inp in spec.inputs)
        if "pull_request" in spec.trigger.on:
            seeded.update({"diff", "plan"})
        for step in spec.steps:
            consumes: set[str] = set(step.consumes)
            agent = agents.get(step.agent)
            if agent is not None:
                consumes.update(agent.consumes)
            if not consumes:
                continue
            ancestor_ids = _ancestors(step.id, adjacency)
            produced_upstream: set[str] = set()
            for anc_id in ancestor_ids:
                anc_step = spec.step_by_id(anc_id)
                if anc_step is not None:
                    produced_upstream.update(anc_step.produces)
                    anc_agent = agents.get(anc_step.agent) if anc_step else None
                    if anc_agent is not None:
                        produced_upstream.update(anc_agent.produces)
            for kind in sorted(consumes):
                if kind in seeded:
                    continue
                if kind not in produced_upstream:
                    errors.append(
                        f"step '{step.id}' consumes '{kind}' but no transitive "
                        f"ancestor produces it"
                    )

    # --- when expressions are syntactically valid -------------------------
    for step in spec.steps:
        if step.when is not None:
            try:
                whenexpr.evaluate(step.when, {})
            except whenexpr.WhenSyntaxError as exc:
                errors.append(f"step '{step.id}': invalid when expression: {exc}")

    return errors
