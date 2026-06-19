"""Robust path resolution relative to the ``.pipeline`` root.

The orchestrator lives at ``.pipeline/orchestrator/``. Default agents,
workflows, and runs directories are siblings under ``.pipeline/``. These
helpers resolve those locations from the package's own file location so the
CLI works regardless of the current working directory.
"""

from __future__ import annotations

import os


def pipeline_root() -> str:
    """Absolute path to the ``.pipeline`` directory (parent of this package)."""
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.dirname(here)


def agents_dir() -> str:
    return os.path.join(pipeline_root(), "agents")


def workflows_dir() -> str:
    return os.path.join(pipeline_root(), "workflows")


def runs_dir() -> str:
    return os.path.join(pipeline_root(), "runs")


def workflow_path(workflows_directory: str, name: str) -> str:
    """Resolve a workflow file by name within ``workflows_directory``.

    Accepts a bare name ('feature'), a name with extension ('feature.yaml'),
    or an explicit path. Tries ``.yaml`` then ``.yml``.
    """
    if os.path.isfile(name):
        return name
    if name.endswith((".yaml", ".yml")):
        candidate = os.path.join(workflows_directory, name)
        if os.path.isfile(candidate):
            return candidate
        raise ValueError(f"workflow file not found: {candidate}")
    for ext in (".yaml", ".yml"):
        candidate = os.path.join(workflows_directory, name + ext)
        if os.path.isfile(candidate):
            return candidate
    raise ValueError(
        f"workflow '{name}' not found in {workflows_directory} (.yaml/.yml)"
    )
