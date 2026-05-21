"""Build-caseplan adapter helpers shared by MCP and HTTP transports."""

from __future__ import annotations

import inspect
from collections.abc import Callable, Mapping
from typing import Any, Protocol

from caseprep.core import (
    BuildCasePlanRequest,
    BuildCasePlanResult,
    CasePlanBuilder,
    CasePrepConfigurationError,
    CasePrepError,
    CasePrepExternalServiceError,
    CasePrepPersistenceError,
    CasePrepProvenanceError,
    CasePrepValidationError,
)


class CasePlanBuilderLike(Protocol):
    async def build_case_plan(
        self,
        request: BuildCasePlanRequest,
    ) -> BuildCasePlanResult:
        ...


BuilderFactory = Callable[[], CasePlanBuilderLike]


def slugify_caseplan_topic(topic: str) -> str:
    return topic.strip().lower().replace(" ", "-")


def build_caseplan_request(
    arguments: Mapping[str, Any],
) -> BuildCasePlanRequest:
    """Create a core request from transport arguments."""
    options = arguments.get("options") or {}
    if not isinstance(options, dict):
        raise CasePrepValidationError(
            "options must be an object",
            details={"field": "options"},
        )

    return BuildCasePlanRequest(
        topic=arguments.get("topic"),
        case_input=arguments.get("case_input"),
        output_dir=arguments.get("output_dir") or None,
        max_per_category=arguments.get("max_per_category", 3),
        profile_hint=arguments.get("profile_hint"),
        structured_output=arguments.get("structured_output", False),
        options=dict(options),
    )


async def _maybe_await(value):
    if inspect.isawaitable(value):
        return await value
    return value


async def build_caseplan_result(
    arguments: Mapping[str, Any],
    *,
    builder_factory: BuilderFactory = CasePlanBuilder,
) -> BuildCasePlanResult:
    """Build a case plan and keep the structured result available to adapters."""
    request = build_caseplan_request(arguments)
    builder = builder_factory()
    return await _maybe_await(builder.build_case_plan(request))


async def build_caseplan_markdown(
    arguments: Mapping[str, Any],
    *,
    builder_factory: BuilderFactory = CasePlanBuilder,
) -> str:
    """Build a case plan and return the legacy markdown/text transport output."""
    result = await build_caseplan_result(
        arguments,
        builder_factory=builder_factory,
    )
    return result.markdown


def caseprep_error_status(exc: CasePrepError) -> int:
    """Map domain errors to stable HTTP status codes."""
    if isinstance(exc, CasePrepValidationError):
        return 400
    if isinstance(exc, CasePrepProvenanceError):
        return 422
    if isinstance(exc, CasePrepExternalServiceError):
        return 503
    if isinstance(exc, (CasePrepConfigurationError, CasePrepPersistenceError)):
        return 500
    return 500


def caseplan_api_payload(
    result: BuildCasePlanResult,
    *,
    slug: str,
    output_dir: str,
    caseplan_id: int,
) -> dict[str, Any]:
    """Return the stable FastAPI /api/build response payload."""
    return {
        "slug": slug,
        "topic": result.topic,
        "output_dir": output_dir,
        "summary": result.markdown,
        "caseplan_id": caseplan_id,
    }
