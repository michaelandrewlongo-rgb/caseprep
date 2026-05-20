"""Persistence abstractions for CasePrep core runs."""

from __future__ import annotations

import json
import os
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Mapping, Protocol

from caseprep.core.contracts import BuildCasePlanRequest, BuildCasePlanResult
from caseprep.core.errors import (
    CasePrepConfigurationError,
    CasePrepPersistenceError,
)


@dataclass(frozen=True)
class PersistedRun:
    """Reference to persisted run metadata."""

    run_id: str
    metadata_path: Path
    artifact_paths: list[Path]
    sqlite_path: Path | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "run_id": self.run_id,
            "metadata_path": str(self.metadata_path),
            "sqlite_path": str(self.sqlite_path) if self.sqlite_path else None,
            "artifact_paths": [str(path) for path in self.artifact_paths],
        }


class CasePrepRunStore(Protocol):
    """Storage backend for CasePrep run metadata."""

    def save_run(
        self,
        result: BuildCasePlanResult,
        *,
        run_id: str | None = None,
    ) -> PersistedRun:
        ...


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _new_run_id() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{stamp}-{uuid.uuid4().hex[:12]}"


def _to_jsonable(value: object) -> object:
    if hasattr(value, "to_dict"):
        return value.to_dict()  # type: ignore[no-any-return]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _to_jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_to_jsonable(item) for item in value]
    if isinstance(value, tuple):
        return [_to_jsonable(item) for item in value]
    return value


def _json_dumps(value: object) -> str:
    return json.dumps(_to_jsonable(value), indent=2, sort_keys=True)


def _resolve_bool(value: object, *, field: str) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    raw = str(value).strip().lower()
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off", ""}:
        return False
    raise CasePrepConfigurationError(
        f"{field} must be a boolean value",
        details={"field": field, "value": value},
    )


def _profile_from_result(result: BuildCasePlanResult) -> str:
    profile = result.structured.get("profile")
    if isinstance(profile, dict):
        name = profile.get("name")
        if isinstance(name, str) and name.strip():
            return name.strip()

    shadow = result.shadow
    if isinstance(shadow, dict):
        structured = shadow.get("structured")
        if isinstance(structured, dict):
            shadow_profile = structured.get("profile")
            if isinstance(shadow_profile, dict):
                name = shadow_profile.get("name")
                if isinstance(name, str) and name.strip():
                    return name.strip()

    return "unknown"


def _artifact_paths(result: BuildCasePlanResult) -> list[Path]:
    return [artifact.path for artifact in result.artifacts]


class FileSystemCasePrepStore:
    """Filesystem run history with optional SQLite metadata index."""

    def __init__(
        self,
        root_dir: Path | str,
        *,
        sqlite_path: Path | str | None = None,
        now_factory: Callable[[], str] | None = None,
        run_id_factory: Callable[[], str] | None = None,
    ) -> None:
        self.root_dir = Path(root_dir)
        self.sqlite_path = Path(sqlite_path) if sqlite_path is not None else None
        self._now_factory = now_factory or _utc_now
        self._run_id_factory = run_id_factory or _new_run_id

    def save_run(
        self,
        result: BuildCasePlanResult,
        *,
        run_id: str | None = None,
    ) -> PersistedRun:
        resolved_run_id = run_id or self._run_id_factory()
        run_dir = self.root_dir / "runs" / resolved_run_id
        metadata_path = run_dir / "run.json"
        artifact_paths = _artifact_paths(result)
        payload = self._build_payload(
            result,
            run_id=resolved_run_id,
            artifact_paths=artifact_paths,
        )

        try:
            run_dir.mkdir(parents=True, exist_ok=True)
            metadata_path.write_text(_json_dumps(payload) + "\n", encoding="utf-8")
            if self.sqlite_path is not None:
                self._save_sqlite_metadata(payload, metadata_path)
        except (OSError, sqlite3.Error) as exc:
            raise CasePrepPersistenceError(
                "Failed to persist CasePrep run metadata",
                details={
                    "run_id": resolved_run_id,
                    "metadata_path": str(metadata_path),
                    "sqlite_path": str(self.sqlite_path) if self.sqlite_path else None,
                    "cause": str(exc),
                },
            ) from exc

        return PersistedRun(
            run_id=resolved_run_id,
            metadata_path=metadata_path,
            artifact_paths=artifact_paths,
            sqlite_path=self.sqlite_path,
        )

    def list_runs(self, limit: int = 50) -> list[dict[str, object]]:
        runs_dir = self.root_dir / "runs"
        if not runs_dir.exists():
            return []

        payloads: list[dict[str, object]] = []
        for metadata_path in runs_dir.glob("*/run.json"):
            try:
                payload = json.loads(metadata_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise CasePrepPersistenceError(
                    "Failed to read CasePrep run metadata",
                    details={"metadata_path": str(metadata_path), "cause": str(exc)},
                ) from exc
            payloads.append(payload)

        payloads.sort(key=lambda item: str(item.get("created_at", "")), reverse=True)
        return payloads[:limit]

    def _build_payload(
        self,
        result: BuildCasePlanResult,
        *,
        run_id: str,
        artifact_paths: list[Path],
    ) -> dict[str, object]:
        return {
            "run_id": run_id,
            "created_at": self._now_factory(),
            "topic": result.topic,
            "profile": _profile_from_result(result),
            "mode": result.mode,
            "output_dir": str(result.output_dir) if result.output_dir else None,
            "artifact_paths": [str(path) for path in artifact_paths],
            "artifacts": [artifact.to_dict() for artifact in result.artifacts],
            "evidence": [record.to_dict() for record in result.evidence],
            "provenance": [record.to_dict() for record in result.provenance],
            "warnings": list(result.warnings),
            "structured": _to_jsonable(result.structured),
            "shadow": _to_jsonable(result.shadow),
        }

    def _save_sqlite_metadata(
        self,
        payload: dict[str, object],
        metadata_path: Path,
    ) -> None:
        assert self.sqlite_path is not None
        self.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.sqlite_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS caseprep_runs (
                    run_id TEXT PRIMARY KEY,
                    topic TEXT NOT NULL,
                    profile TEXT NOT NULL,
                    mode TEXT NOT NULL,
                    metadata_path TEXT NOT NULL,
                    artifact_paths TEXT NOT NULL,
                    warnings TEXT NOT NULL,
                    evidence_count INTEGER NOT NULL,
                    provenance_count INTEGER NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                INSERT OR REPLACE INTO caseprep_runs (
                    run_id, topic, profile, mode, metadata_path, artifact_paths,
                    warnings, evidence_count, provenance_count, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    payload["run_id"],
                    payload["topic"],
                    payload["profile"],
                    payload["mode"],
                    str(metadata_path),
                    json.dumps(payload["artifact_paths"], sort_keys=True),
                    json.dumps(payload["warnings"], sort_keys=True),
                    len(payload["evidence"]) if isinstance(payload["evidence"], list) else 0,
                    len(payload["provenance"])
                    if isinstance(payload["provenance"], list)
                    else 0,
                    payload["created_at"],
                ),
            )


def resolve_caseprep_store(
    request: BuildCasePlanRequest,
    *,
    env: Mapping[str, str] | None = None,
) -> CasePrepRunStore | None:
    """Resolve an optional run store for a core build request."""
    values = env if env is not None else os.environ
    options = request.options
    persistence_dir = options.get("persistence_dir") or values.get(
        "CASEPREP_PERSISTENCE_DIR"
    )
    raw_persist = options.get(
        "persist_runs",
        values.get("CASEPREP_PERSIST_RUNS", "0"),
    )

    if not persistence_dir and not _resolve_bool(raw_persist, field="persist_runs"):
        return None

    root_dir = (
        Path(str(persistence_dir))
        if persistence_dir
        else request.resolved_output_dir() / ".caseprep"
    )
    sqlite_path = options.get("sqlite_metadata_path") or values.get(
        "CASEPREP_SQLITE_METADATA_PATH"
    )
    return FileSystemCasePrepStore(
        root_dir,
        sqlite_path=Path(str(sqlite_path)) if sqlite_path else None,
    )
