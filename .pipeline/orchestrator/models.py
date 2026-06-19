"""Domain models for the agentic pipeline.

Dataclasses mirroring the schemas in ARCHITECTURE.md:
  - §3 agent definition frontmatter  -> :class:`AgentDef`
  - §5 workflow spec                  -> :class:`WorkflowSpec`, :class:`Step`,
                                          :class:`Trigger`
  - §4 gates                          -> :class:`Gate`
  - §6 artifacts & run state          -> :class:`RunManifest`, :class:`StepState`,
                                          :class:`StepStatus`
  - model id mapping                  -> :class:`Model`

These types are deliberately plain: loaders build them, the validator checks
them, the planner consumes them, and the engine mutates only run state.
"""

from __future__ import annotations

import enum
from dataclasses import asdict, dataclass, field
from typing import Any, Optional


class Gate(str, enum.Enum):
    """Quality bar a step must clear before the run proceeds (ARCHITECTURE §4)."""

    NONE = "none"
    ADVISORY = "advisory"
    BLOCKING = "blocking"
    HUMAN = "human"

    @classmethod
    def parse(cls, value: Optional[str]) -> "Gate":
        if value is None:
            return cls.NONE
        try:
            return cls(str(value).strip().lower())
        except ValueError as exc:  # pragma: no cover - defensive
            raise ValueError(
                f"unknown gate '{value}'; expected one of {[g.value for g in cls]}"
            ) from exc


class StepStatus(str, enum.Enum):
    """Lifecycle of a single step (ARCHITECTURE §6).

    pending -> running -> passed | blocked | skipped | failed
    """

    PENDING = "pending"
    RUNNING = "running"
    PASSED = "passed"
    BLOCKED = "blocked"
    SKIPPED = "skipped"
    FAILED = "failed"


class Model(str, enum.Enum):
    """Short model aliases used in agent frontmatter (ARCHITECTURE §3).

    The alias maps to a concrete claude-* id at runtime via :attr:`model_id`.
    """

    OPUS = "opus"
    SONNET = "sonnet"
    HAIKU = "haiku"

    @classmethod
    def parse(cls, value: str) -> "Model":
        try:
            return cls(str(value).strip().lower())
        except ValueError as exc:
            raise ValueError(
                f"unknown model '{value}'; expected one of {[m.value for m in cls]}"
            ) from exc

    @property
    def model_id(self) -> str:
        """Concrete claude-* model identifier for this alias."""
        return _MODEL_IDS[self]


_MODEL_IDS: dict[Model, str] = {
    Model.OPUS: "claude-opus-4-8",
    Model.SONNET: "claude-sonnet-4-6",
    Model.HAIKU: "claude-haiku-4-5-20251001",
}


@dataclass
class AgentDef:
    """An agent role definition parsed from ``agents/<name>.md`` (ARCHITECTURE §3).

    Frontmatter fields plus the markdown ``body`` (the agent's system prompt).
    """

    name: str
    discipline: str
    model: Model
    tools: list[str] = field(default_factory=list)
    produces: list[str] = field(default_factory=list)
    consumes: list[str] = field(default_factory=list)
    gate: Gate = Gate.NONE
    escalates_to: Optional[str] = None
    max_turns: int = 40
    body: str = ""

    @property
    def model_id(self) -> str:
        return self.model.model_id


@dataclass
class Trigger:
    """How a workflow is started (ARCHITECTURE §5)."""

    on: list[str] = field(default_factory=list)
    labels: list[str] = field(default_factory=list)
    cron: Optional[str] = None


@dataclass
class InputSpec:
    """A named input the run is seeded with (ARCHITECTURE §5)."""

    name: str
    required: bool = False
    description: str = ""


@dataclass
class Defaults:
    """Run-wide defaults (ARCHITECTURE §5/§8)."""

    max_retries: int = 1
    budget_usd: float = 0.0


@dataclass
class Step:
    """One node in the workflow DAG = one agent doing one job (ARCHITECTURE §5)."""

    id: str
    agent: str
    depends_on: list[str] = field(default_factory=list)
    when: Optional[str] = None
    produces: list[str] = field(default_factory=list)
    consumes: list[str] = field(default_factory=list)
    # Per-step gate override; if None the agent's default gate applies.
    gate: Optional[Gate] = None


@dataclass
class WorkflowSpec:
    """A declarative DAG composing agents into a pipeline (ARCHITECTURE §5)."""

    name: str
    description: str = ""
    version: int = 1
    trigger: Trigger = field(default_factory=Trigger)
    inputs: list[InputSpec] = field(default_factory=list)
    defaults: Defaults = field(default_factory=Defaults)
    steps: list[Step] = field(default_factory=list)

    def step_by_id(self, step_id: str) -> Optional[Step]:
        for step in self.steps:
            if step.id == step_id:
                return step
        return None


@dataclass
class StepState:
    """Mutable per-step state recorded in the run manifest (ARCHITECTURE §6)."""

    id: str
    agent: str
    status: StepStatus = StepStatus.PENDING
    gate: Gate = Gate.NONE
    reason: str = ""
    verdict: Optional[str] = None  # pass | block | warn (for gated steps)
    produced: list[str] = field(default_factory=list)
    needs_human: bool = False
    started_at: Optional[str] = None
    ended_at: Optional[str] = None
    attempts: int = 0
    cost_usd: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["status"] = self.status.value
        data["gate"] = self.gate.value
        return data


@dataclass
class RunManifest:
    """Single source of truth for a run's state, persisted as ``run.json``."""

    run_id: str
    workflow: str
    status: str = "running"  # running | passed | blocked | failed | needs_human
    inputs: dict[str, Any] = field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""
    budget_usd: float = 0.0
    cost_usd: float = 0.0
    executor: str = ""
    steps: list[StepState] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def step_state(self, step_id: str) -> Optional[StepState]:
        for state in self.steps:
            if state.id == step_id:
                return state
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "workflow": self.workflow,
            "status": self.status,
            "inputs": self.inputs,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "budget_usd": self.budget_usd,
            "cost_usd": self.cost_usd,
            "executor": self.executor,
            "steps": [s.to_dict() for s in self.steps],
            "notes": list(self.notes),
        }
