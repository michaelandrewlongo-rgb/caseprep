"""CasePrep domain error taxonomy."""

from __future__ import annotations

from typing import Any


class CasePrepError(Exception):
    """Base class for transport-neutral CasePrep domain errors."""

    code = "caseprep_error"

    def __init__(
        self,
        message: str,
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}

    def to_dict(self) -> dict[str, Any]:
        return {
            "error": self.code,
            "message": self.message,
            "details": self.details,
        }


class CasePrepValidationError(CasePrepError):
    code = "validation_error"


class CasePrepConfigurationError(CasePrepError):
    code = "configuration_error"


class CasePrepExternalServiceError(CasePrepError):
    code = "external_service_error"


class CasePrepProvenanceError(CasePrepError):
    code = "provenance_error"


class CasePrepPersistenceError(CasePrepError):
    code = "persistence_error"
