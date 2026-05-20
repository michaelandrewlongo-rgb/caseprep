"""CasePrep core engine facade.

The first refactor slice keeps the facade additive: legacy mode delegates to
the current implementation, shadow mode returns legacy output, and core mode is
reserved until the independent core pipeline lands.
"""

from __future__ import annotations

import inspect
import os
from dataclasses import replace
from typing import Awaitable, Callable, Mapping

from .contracts import BuildCasePlanRequest, BuildCasePlanResult, CoreMode
from .errors import CasePrepConfigurationError


VALID_CORE_MODES: set[str] = {"legacy", "shadow", "core"}

LegacyBuildCasePlan = Callable[
    [BuildCasePlanRequest],
    str | BuildCasePlanResult | Awaitable[str | BuildCasePlanResult],
]
CoreBuildCasePlan = Callable[
    [BuildCasePlanRequest],
    BuildCasePlanResult | Awaitable[BuildCasePlanResult],
]


def resolve_core_mode(env: Mapping[str, str] | None = None) -> CoreMode:
    values = env if env is not None else os.environ
    raw_mode = values.get("CASEPREP_CORE_MODE", "legacy").strip().lower()
    mode = raw_mode or "legacy"
    if mode not in VALID_CORE_MODES:
        raise CasePrepConfigurationError(
            "CASEPREP_CORE_MODE must be one of legacy, shadow, or core",
            details={"field": "CASEPREP_CORE_MODE", "value": raw_mode},
        )
    return mode  # type: ignore[return-value]


async def _maybe_await(value):
    if inspect.isawaitable(value):
        return await value
    return value


async def _default_legacy_build_caseplan(request: BuildCasePlanRequest) -> str:
    from caseprep.mcp_server import _legacy_handle_build_caseplan

    return await _legacy_handle_build_caseplan(request.to_legacy_args())


class CasePlanBuilder:
    """Facade for building case plans through legacy, shadow, or core mode."""

    def __init__(
        self,
        *,
        mode: CoreMode | None = None,
        legacy_builder: LegacyBuildCasePlan | None = None,
        core_builder: CoreBuildCasePlan | None = None,
        env: Mapping[str, str] | None = None,
    ) -> None:
        self.mode = mode or resolve_core_mode(env)
        if self.mode not in VALID_CORE_MODES:
            raise CasePrepConfigurationError(
                "mode must be one of legacy, shadow, or core",
                details={"field": "mode", "value": self.mode},
            )
        self._legacy_builder = legacy_builder or _default_legacy_build_caseplan
        self._core_builder = core_builder

    async def build_case_plan(
        self,
        request: BuildCasePlanRequest,
    ) -> BuildCasePlanResult:
        if self.mode == "legacy":
            return await self._run_legacy(request, mode="legacy")
        if self.mode == "shadow":
            return await self._run_shadow(request)
        return await self._run_core(request)

    async def _run_legacy(
        self,
        request: BuildCasePlanRequest,
        *,
        mode: CoreMode,
    ) -> BuildCasePlanResult:
        raw_result = await _maybe_await(self._legacy_builder(request))
        return self._coerce_result(raw_result, request, mode=mode)

    async def _run_shadow(self, request: BuildCasePlanRequest) -> BuildCasePlanResult:
        legacy_result = await self._run_legacy(request, mode="shadow")
        if self._core_builder is None:
            return replace(
                legacy_result,
                warnings=legacy_result.warnings + [
                    "CASEPREP_CORE_MODE=shadow ran legacy only because no core builder is configured."
                ],
            )

        core_result = await _maybe_await(self._core_builder(request))
        return replace(
            legacy_result,
            shadow={
                "mode": core_result.mode,
                "markdown": core_result.markdown,
                "structured": core_result.structured,
                "warnings": core_result.warnings,
            },
        )

    async def _run_core(self, request: BuildCasePlanRequest) -> BuildCasePlanResult:
        if self._core_builder is None:
            raise CasePrepConfigurationError(
                "CASEPREP_CORE_MODE=core requested, but core builder is not configured",
                details={"field": "CASEPREP_CORE_MODE", "value": "core"},
            )
        raw_result = await _maybe_await(self._core_builder(request))
        return self._coerce_result(raw_result, request, mode="core")

    @staticmethod
    def _coerce_result(
        raw_result: str | BuildCasePlanResult,
        request: BuildCasePlanRequest,
        *,
        mode: CoreMode,
    ) -> BuildCasePlanResult:
        if isinstance(raw_result, BuildCasePlanResult):
            return replace(raw_result, mode=mode)
        return BuildCasePlanResult(
            topic=request.topic,
            markdown=raw_result,
            output_dir=request.resolved_output_dir(),
            mode=mode,
        )
