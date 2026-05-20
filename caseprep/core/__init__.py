"""Shared CasePrep core contracts and facade."""

from .contracts import (
    ArtifactRef,
    BuildCasePlanRequest,
    BuildCasePlanResult,
    EvidenceRecord,
    ProvenanceRecord,
)
from .engine import CasePlanBuilder, resolve_core_mode
from .errors import (
    CasePrepConfigurationError,
    CasePrepError,
    CasePrepExternalServiceError,
    CasePrepPersistenceError,
    CasePrepProvenanceError,
    CasePrepValidationError,
)

__all__ = [
    "ArtifactRef",
    "BuildCasePlanRequest",
    "BuildCasePlanResult",
    "CasePlanBuilder",
    "CasePrepConfigurationError",
    "CasePrepError",
    "CasePrepExternalServiceError",
    "CasePrepPersistenceError",
    "CasePrepProvenanceError",
    "CasePrepValidationError",
    "EvidenceRecord",
    "ProvenanceRecord",
    "resolve_core_mode",
]
