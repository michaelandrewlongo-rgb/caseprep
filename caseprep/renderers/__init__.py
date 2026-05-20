"""Pure renderer feature flags and comparison helpers."""

from __future__ import annotations

import os
from collections.abc import Mapping

from caseprep.core import CasePrepConfigurationError


def _resolve_boolean_flag(
    name: str,
    *,
    env: Mapping[str, str] | None = None,
) -> bool:
    values = env if env is not None else os.environ
    raw_value = values.get(name, "0").strip()
    if raw_value == "" or raw_value == "0":
        return False
    if raw_value == "1":
        return True
    raise CasePrepConfigurationError(
        f"{name} must be 0 or 1",
        details={"field": name, "value": raw_value},
    )


def resolve_dual_write_enabled(env: Mapping[str, str] | None = None) -> bool:
    """Return whether renderers should execute legacy and core paths."""
    return _resolve_boolean_flag("CASEPREP_DUAL_WRITE", env=env)


def resolve_compare_outputs_enabled(env: Mapping[str, str] | None = None) -> bool:
    """Return whether dual-write output comparison is enabled."""
    return _resolve_boolean_flag("CASEPREP_COMPARE_OUTPUTS", env=env)


def compare_rendered_outputs(
    expected: dict[str, str],
    actual: dict[str, str],
) -> list[str]:
    """Return deterministic file-level differences between rendered outputs."""
    issues: list[str] = []
    expected_names = set(expected)
    actual_names = set(actual)

    for filename in sorted(expected_names - actual_names):
        issues.append(f"Missing rendered file {filename}")
    for filename in sorted(actual_names - expected_names):
        issues.append(f"Unexpected rendered file {filename}")
    for filename in sorted(expected_names & actual_names):
        if expected[filename] != actual[filename]:
            issues.append(f"Changed rendered file {filename}")
    return issues


__all__ = [
    "compare_rendered_outputs",
    "resolve_compare_outputs_enabled",
    "resolve_dual_write_enabled",
]
