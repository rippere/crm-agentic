"""Agentic CI/CD orchestrator.

A substrate-agnostic engine that loads agent definitions and workflow specs
(per .pipeline/ARCHITECTURE.md), validates them, builds a deterministic
execution plan (a DAG grouped into parallel waves), and executes that plan
through a pluggable ``Executor``.

See ``ARCHITECTURE.md`` (the keystone contract) for the schemas this package
conforms to, and ``README.md`` in this directory for usage.
"""

from __future__ import annotations

__all__ = ["__version__"]

__version__ = "0.1.0"
