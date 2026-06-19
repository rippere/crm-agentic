"""Safe evaluator for the ``when`` mini-language (ARCHITECTURE §7).

Supported forms ONLY (no arbitrary code; no eval/exec):
  - ``always``                     -> True
  - ``never``                      -> False
  - ``<value> in <artifact>.<field>``
  - ``<artifact>.<field> == <value>``
  - ``<artifact>.<field> != <value>``

Evaluation rules:
  - ``<artifact>`` is looked up in the supplied artifacts dict (name -> dict).
  - ``<field>`` is read from that artifact's mapping.
  - An unknown artifact or field makes the whole condition **False**, and the
    reason is reported (so the planner can record why a step was skipped).
  - ``<value>`` is a bare token (unquoted) or a single/double-quoted string.
    Numeric / boolean literals are compared by their string form too, so that
    ``status == pass`` and ``count == 3`` both work intuitively.

The public entry point is :func:`evaluate`, returning ``(result, reason)``.
"""

from __future__ import annotations

import re
from typing import Any, Mapping, Tuple

# An artifact reference like ``plan.touches``.
_REF = re.compile(r"^[A-Za-z_][\w-]*\.[A-Za-z_][\w-]*$")


class WhenSyntaxError(ValueError):
    """Raised when a ``when`` expression is not in the §7 grammar."""


def _strip_quotes(token: str) -> str:
    token = token.strip()
    if len(token) >= 2 and token[0] == token[-1] and token[0] in {'"', "'"}:
        return token[1:-1]
    return token


def _resolve_ref(
    ref: str, artifacts: Mapping[str, Any]
) -> Tuple[bool, Any, str]:
    """Resolve ``artifact.field``.

    Returns (found, value, reason). ``found`` is False (with a reason) when the
    artifact or field is missing.
    """
    artifact_name, _, field_name = ref.partition(".")
    if artifact_name not in artifacts:
        return False, None, f"artifact '{artifact_name}' not available"
    artifact = artifacts[artifact_name]
    if not isinstance(artifact, Mapping):
        return False, None, f"artifact '{artifact_name}' is not a mapping"
    if field_name not in artifact:
        return False, None, f"field '{field_name}' missing on artifact '{artifact_name}'"
    return True, artifact[field_name], ""


def _coerce_membership(value: Any) -> list[str]:
    """Normalise a field value into a list of string members for ``in``."""
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, (list, tuple, set)):
        return [str(v) for v in value]
    if isinstance(value, Mapping):
        return [str(k) for k in value.keys()]
    return [str(value)]


def evaluate(expr: str | None, artifacts: Mapping[str, Any]) -> Tuple[bool, str]:
    """Evaluate a ``when`` expression against known artifacts.

    Returns ``(result, reason)``. A ``None``/empty expression is treated as
    ``always`` (the step is unconditional). Raises :class:`WhenSyntaxError` for
    expressions outside the §7 grammar.
    """
    if expr is None:
        return True, "no condition"
    text = expr.strip()
    if text == "":
        return True, "no condition"

    if text == "always":
        return True, "always"
    if text == "never":
        return False, "never"

    # Form: <value> in <artifact>.<field>
    m = re.match(r"^(.+?)\s+in\s+(\S+)$", text)
    if m:
        value = _strip_quotes(m.group(1))
        ref = m.group(2).strip()
        if not _REF.match(ref):
            raise WhenSyntaxError(
                f"invalid 'in' expression: right side must be artifact.field, got '{ref}'"
            )
        found, field_value, why = _resolve_ref(ref, artifacts)
        if not found:
            return False, why
        members = _coerce_membership(field_value)
        if value in members:
            return True, f"'{value}' in {ref}"
        return False, f"'{value}' not in {ref}"

    # Forms: <artifact>.<field> == <value>  /  != <value>
    m = re.match(r"^(\S+)\s*(==|!=)\s*(.+)$", text)
    if m:
        ref = m.group(1).strip()
        op = m.group(2)
        value = _strip_quotes(m.group(3))
        if not _REF.match(ref):
            raise WhenSyntaxError(
                f"invalid comparison: left side must be artifact.field, got '{ref}'"
            )
        found, field_value, why = _resolve_ref(ref, artifacts)
        if not found:
            # Missing artifact/field => condition is False either way.
            return False, why
        equal = str(field_value) == value
        if op == "==":
            return (equal, f"{ref} == '{value}'" if equal else f"{ref} != '{value}'")
        return (not equal, f"{ref} != '{value}'" if not equal else f"{ref} == '{value}'")

    raise WhenSyntaxError(
        f"unsupported 'when' expression: {expr!r}; "
        "allowed: 'always', 'never', '<v> in a.f', 'a.f == v', 'a.f != v'"
    )
