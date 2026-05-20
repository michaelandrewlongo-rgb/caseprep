"""Tests for CasePrep core persistence abstractions."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from caseprep.core import (
    ArtifactRef,
    BuildCasePlanRequest,
    BuildCasePlanResult,
    EvidenceRecord,
    ProvenanceRecord,
)


def _result(tmp_path: Path) -> BuildCasePlanResult:
    return BuildCasePlanResult(
        topic="aneurysm clipping",
        markdown="# Core Case Plan",
        output_dir=tmp_path / "aneurysm-caseprep",
        mode="core",
        artifacts=[
            ArtifactRef(
                path=tmp_path / "aneurysm-caseprep" / "README.md",
                kind="markdown",
                media_type="text/markdown",
            )
        ],
        evidence=[
            EvidenceRecord(
                id="pmid-1",
                source="pubmed",
                title="Aneurysm evidence",
                url="https://pubmed.ncbi.nlm.nih.gov/1/",
                metadata={"axis": "Outcomes / Evidence"},
            )
        ],
        provenance=[
            ProvenanceRecord(
                field_path="profile",
                source_ids=[],
                value_status="generated",
                generated_by="profile_classifier",
            ),
            ProvenanceRecord(
                field_path="sections.outcomes-evidence",
                source_ids=["pmid-1"],
                value_status="generated",
            ),
        ],
        structured={"profile": {"name": "vascular"}},
        warnings=["limited local corpus evidence"],
    )


def test_filesystem_store_saves_run_metadata_and_artifact_paths(tmp_path):
    from caseprep.persistence import FileSystemCasePrepStore

    store = FileSystemCasePrepStore(
        tmp_path / ".caseprep",
        now_factory=lambda: "2026-05-20T21:40:00Z",
    )

    persisted = store.save_run(_result(tmp_path), run_id="run-001")

    assert persisted.run_id == "run-001"
    assert persisted.metadata_path == tmp_path / ".caseprep" / "runs" / "run-001" / "run.json"
    assert persisted.artifact_paths == [tmp_path / "aneurysm-caseprep" / "README.md"]

    payload = json.loads(persisted.metadata_path.read_text(encoding="utf-8"))
    assert payload["run_id"] == "run-001"
    assert payload["created_at"] == "2026-05-20T21:40:00Z"
    assert payload["topic"] == "aneurysm clipping"
    assert payload["profile"] == "vascular"
    assert payload["artifact_paths"] == [str(tmp_path / "aneurysm-caseprep" / "README.md")]
    assert payload["warnings"] == ["limited local corpus evidence"]
    assert payload["evidence"][0]["id"] == "pmid-1"
    assert payload["provenance"][1]["source_ids"] == ["pmid-1"]

    assert store.list_runs() == [payload]


def test_filesystem_store_can_dual_write_sqlite_metadata(tmp_path):
    from caseprep.persistence import FileSystemCasePrepStore

    sqlite_path = tmp_path / "caseprep-runs.sqlite3"
    store = FileSystemCasePrepStore(
        tmp_path / ".caseprep",
        sqlite_path=sqlite_path,
        now_factory=lambda: "2026-05-20T21:45:00Z",
    )

    store.save_run(_result(tmp_path), run_id="run-sqlite")

    with sqlite3.connect(sqlite_path) as conn:
        row = conn.execute(
            "SELECT run_id, topic, profile, mode, evidence_count, provenance_count, artifact_paths "
            "FROM caseprep_runs WHERE run_id = ?",
            ("run-sqlite",),
        ).fetchone()

    assert row == (
        "run-sqlite",
        "aneurysm clipping",
        "vascular",
        "core",
        1,
        2,
        json.dumps([str(tmp_path / "aneurysm-caseprep" / "README.md")], sort_keys=True),
    )


@pytest.mark.asyncio
async def test_core_builder_persists_run_when_store_is_configured(tmp_path):
    from caseprep.core.builder import CoreRetrieverSet, build_core_case_plan
    from caseprep.persistence import PersistedRun

    class EmptyPubMedRetriever:
        async def retrieve(
            self,
            query,
            *,
            max_results=10,
            filter_type=None,
            include_abstracts=True,
        ):
            return []

    class EmptyRadiologyRetriever:
        async def retrieve(self, query, *, max_results=5, modality=None):
            return []

    class EmptyCorpusRetriever:
        def retrieve(self, fts_query, *, subdomain=None, top_n=8):
            return []

    class CapturingStore:
        def __init__(self):
            self.saved_results = []

        def save_run(self, result, *, run_id=None):
            self.saved_results.append((result, run_id))
            return PersistedRun(
                run_id=run_id or "generated-run",
                metadata_path=tmp_path / "run.json",
                artifact_paths=[],
                sqlite_path=None,
            )

    store = CapturingStore()

    result = await build_core_case_plan(
        BuildCasePlanRequest(topic="aneurysm clipping", output_dir=tmp_path),
        retrievers=CoreRetrieverSet(
            pubmed=EmptyPubMedRetriever(),
            radiology=EmptyRadiologyRetriever(),
            corpus=EmptyCorpusRetriever(),
        ),
        store=store,
        run_id="core-run",
    )

    assert store.saved_results == [(result, "core-run")]
    assert result.structured["persistence"] == {
        "run_id": "core-run",
        "metadata_path": str(tmp_path / "run.json"),
        "sqlite_path": None,
        "artifact_paths": [],
    }


@pytest.mark.asyncio
async def test_core_builder_persists_to_output_history_when_requested(tmp_path):
    from caseprep.core.builder import CoreRetrieverSet, build_core_case_plan

    class EmptyPubMedRetriever:
        async def retrieve(
            self,
            query,
            *,
            max_results=10,
            filter_type=None,
            include_abstracts=True,
        ):
            return []

    class EmptyRadiologyRetriever:
        async def retrieve(self, query, *, max_results=5, modality=None):
            return []

    class EmptyCorpusRetriever:
        def retrieve(self, fts_query, *, subdomain=None, top_n=8):
            return []

    output_dir = tmp_path / "aneurysm-caseprep"
    request = BuildCasePlanRequest(
        topic="aneurysm clipping",
        output_dir=output_dir,
        options={"persist_runs": True},
    )

    result = await build_core_case_plan(
        request,
        retrievers=CoreRetrieverSet(
            pubmed=EmptyPubMedRetriever(),
            radiology=EmptyRadiologyRetriever(),
            corpus=EmptyCorpusRetriever(),
        ),
        run_id="requested-run",
    )

    metadata_path = output_dir / ".caseprep" / "runs" / "requested-run" / "run.json"
    assert metadata_path.exists()
    assert result.structured["persistence"]["run_id"] == "requested-run"
    assert result.structured["persistence"]["metadata_path"] == str(metadata_path)
