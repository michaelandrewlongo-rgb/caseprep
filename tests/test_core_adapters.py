"""Tests for adapter routing through the CasePrep core facade."""

from __future__ import annotations

import pytest

from caseprep.core import BuildCasePlanResult
from caseprep.core import CasePrepValidationError


@pytest.mark.asyncio
async def test_mcp_build_caseplan_routes_through_core_facade(monkeypatch):
    import caseprep.mcp_server as mcp_server

    seen_requests = []

    class FakeBuilder:
        async def build_case_plan(self, request):
            seen_requests.append(request)
            return BuildCasePlanResult(
                topic=request.topic,
                markdown="# Case Plan\n\nfacade output",
                output_dir=request.resolved_output_dir(),
                mode="legacy",
            )

    monkeypatch.setattr(mcp_server, "CasePlanBuilder", FakeBuilder)

    output = await mcp_server._handle_build_caseplan({
        "topic": "  vestibular schwannoma  ",
        "max_per_category": 2,
    })

    assert output == "# Case Plan\n\nfacade output"
    assert seen_requests[0].topic == "vestibular schwannoma"
    assert seen_requests[0].max_per_category == 2


@pytest.mark.asyncio
async def test_build_caseplan_adapter_invokes_injected_builder():
    from caseprep.adapters.caseplan import build_caseplan_result

    seen_requests = []

    class FakeBuilder:
        async def build_case_plan(self, request):
            seen_requests.append(request)
            return BuildCasePlanResult(
                topic=request.topic,
                markdown="adapter output",
                output_dir=request.resolved_output_dir(),
                mode="legacy",
                structured={"profile": {"name": "vascular"}},
            )

    result = await build_caseplan_result(
        {
            "topic": "  aneurysm clipping  ",
            "max_per_category": 2,
            "structured_output": True,
        },
        builder_factory=FakeBuilder,
    )

    assert result.markdown == "adapter output"
    assert result.structured == {"profile": {"name": "vascular"}}
    assert seen_requests[0].topic == "aneurysm clipping"
    assert seen_requests[0].max_per_category == 2
    assert seen_requests[0].structured_output is True


def test_caseprep_error_status_maps_domain_errors():
    from caseprep.adapters.caseplan import caseprep_error_status

    assert caseprep_error_status(CasePrepValidationError("bad input")) == 400
