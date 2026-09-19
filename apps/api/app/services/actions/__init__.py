"""
Action modules for the chatbot action bus.

Importing this package self-populates the action_bus registry with every
actuating action: each action module is imported here and its ``SPEC`` registered
via ``action_bus.register``. The read-only MCP tools are registered separately by
``action_bus`` itself at its own import time (it wraps ``mcp_server.TOOLS``).

``app/routers/ai.py`` imports this package once (best-effort) before running the
agentic tool loop so the actuating actions are available to dispatch. Adding a new
actuating action = add a module here and register its ``SPEC`` below.
"""
from __future__ import annotations

from app.services import action_bus
from app.services.actions import discovery as discovery_action

# Register every actuating action's SPEC. register() is keyed by name, so a
# re-import overwrites rather than duplicates.
action_bus.register(discovery_action.SPEC)

__all__ = ["discovery_action"]
