"""Retriever feature flags and normalized retriever exports."""

from __future__ import annotations

import os
from collections.abc import Mapping

from caseprep.core import CasePrepConfigurationError


def resolve_retrievers_v2_enabled(env: Mapping[str, str] | None = None) -> bool:
    values = env if env is not None else os.environ
    raw_value = values.get("CASEPREP_RETRIEVERS_V2", "0").strip()
    if raw_value == "0" or raw_value == "":
        return False
    if raw_value == "1":
        return True
    raise CasePrepConfigurationError(
        "CASEPREP_RETRIEVERS_V2 must be 0 or 1",
        details={"field": "CASEPREP_RETRIEVERS_V2", "value": raw_value},
    )


__all__ = ["resolve_retrievers_v2_enabled"]
