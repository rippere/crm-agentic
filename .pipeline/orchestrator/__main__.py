"""CLI entry point for the orchestrator.

    python -m orchestrator plan --workflow <name>
        Load + validate the workflow, print the DAG, waves, and per-step
        decisions. Exit 0 if valid, non-zero if validation fails.

    python -m orchestrator run --workflow <name> [--input k=v ...]
                               [--executor dryrun|claude-code]
        Validate then execute the workflow. ``--input key=@file`` reads the
        value from a file. Writes a run dir under .pipeline/runs/.

Path overrides: --agents-dir, --workflows-dir, --runs-dir.
"""

from __future__ import annotations

import argparse
import sys
from typing import Any

from . import paths
from .engine import Runner, ValidationError
from .executors import get_executor
from .loader import load_agents, load_workflow
from .planner import plan as build_plan
from .validate import validate_workflow


def _parse_inputs(pairs: list[str]) -> dict[str, Any]:
    inputs: dict[str, Any] = {}
    for pair in pairs or []:
        if "=" not in pair:
            raise SystemExit(f"invalid --input '{pair}'; expected key=value")
        key, _, value = pair.partition("=")
        key = key.strip()
        if value.startswith("@"):
            file_path = value[1:]
            try:
                with open(file_path, "r", encoding="utf-8") as fh:
                    value = fh.read()
            except OSError as exc:
                raise SystemExit(f"cannot read input file '{file_path}': {exc}")
        inputs[key] = value
    return inputs


def _cmd_plan(args: argparse.Namespace) -> int:
    agents_dir = args.agents_dir or paths.agents_dir()
    workflows_dir = args.workflows_dir or paths.workflows_dir()
    try:
        agents = load_agents(agents_dir)
        wf_path = paths.workflow_path(workflows_dir, args.workflow)
        spec = load_workflow(wf_path)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    errors = validate_workflow(spec, agents)
    if errors:
        print(f"workflow '{spec.name}' is INVALID:", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        return 1

    plan = build_plan(spec, agents, artifacts={})
    print(f"workflow: {spec.name}  (version {spec.version})")
    if spec.description:
        print(f"  {spec.description}")
    print(f"trigger.on: {spec.trigger.on or '[]'}")
    print(f"defaults: max_retries={spec.defaults.max_retries} "
          f"budget_usd={spec.defaults.budget_usd}")
    print()
    print("DAG (depends_on):")
    for step in spec.steps:
        deps = ", ".join(step.depends_on) if step.depends_on else "-"
        print(f"  {step.id} <- [{deps}]  (agent: {step.agent})")
    print()
    print("Execution waves (steps in the same wave run in parallel):")
    for i, wave in enumerate(plan.waves, start=1):
        print(f"  wave {i}: {', '.join(wave)}")
    print()
    print("Per-step decision:")
    for step in spec.steps:
        d = plan.decisions[step.id]
        print(f"  {d.step_id:16s} {d.decision:5s} gate={d.gate.value:9s} "
              f"agent={d.agent:12s} reason: {d.reason}")
    print()
    print("VALID")
    return 0


def _cmd_run(args: argparse.Namespace) -> int:
    try:
        executor = get_executor(args.executor)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    runner = Runner(
        executor=executor,
        workflows_dir=args.workflows_dir or paths.workflows_dir(),
        agents_dir=args.agents_dir or paths.agents_dir(),
        runs_dir=args.runs_dir or paths.runs_dir(),
    )

    inputs = _parse_inputs(args.input)

    try:
        result = runner.run(args.workflow, inputs)
    except ValidationError as exc:
        print(f"workflow '{args.workflow}' is INVALID:", file=sys.stderr)
        for err in exc.errors:
            print(f"  - {err}", file=sys.stderr)
        return 1
    except (ValueError, NotImplementedError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    manifest = result.manifest
    print(f"run_id: {manifest.run_id}")
    print(f"run dir: {result.run_dir}")
    print(f"executor: {manifest.executor}")
    print(f"status: {manifest.status}")
    print(f"cost_usd: {manifest.cost_usd:.2f} / budget {manifest.budget_usd:.2f}")
    print()
    print("Step results:")
    for state in manifest.steps:
        verdict = f" verdict={state.verdict}" if state.verdict else ""
        human = " [NEEDS HUMAN]" if state.needs_human else ""
        print(f"  {state.id:16s} {state.status.value:8s} gate={state.gate.value:9s}"
              f"{verdict}{human}  {state.reason}")
    if manifest.notes:
        print()
        print("Notes:")
        for note in manifest.notes:
            print(f"  - {note}")

    # Non-zero exit for blocked/failed; 0 for passed/needs_human (clean pause).
    if manifest.status in ("blocked", "failed"):
        return 1
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="orchestrator",
        description="Agentic CI/CD pipeline orchestrator.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--workflow", required=True, help="workflow name or path")
    common.add_argument("--agents-dir", default=None, help="override agents dir")
    common.add_argument("--workflows-dir", default=None, help="override workflows dir")

    p_plan = sub.add_parser("plan", parents=[common], help="validate + print the plan")
    p_plan.set_defaults(func=_cmd_plan)

    p_run = sub.add_parser("run", parents=[common], help="execute the workflow")
    p_run.add_argument("--input", action="append", default=[],
                       help="key=value or key=@file (repeatable)")
    p_run.add_argument("--executor", default="dryrun",
                       choices=["dryrun", "claude-code"])
    p_run.add_argument("--runs-dir", default=None, help="override runs dir")
    p_run.set_defaults(func=_cmd_run)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
