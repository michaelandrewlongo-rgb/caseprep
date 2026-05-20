"""Transport-agnostic CasePrep core data contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from .errors import CasePrepValidationError


CoreMode = Literal["legacy", "shadow", "core"]


def _slugify_topic(topic: str) -> str:
    return topic.strip().lower().replace(" ", "-")


@dataclass(frozen=True)
class BuildCasePlanRequest:
    """Request to build a CasePrep plan for a topic."""

    topic: str
    output_dir: Path | str | None = None
    max_per_category: int = 5
    profile_hint: str | None = None
    structured_output: bool = False
    options: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        topic = self.topic.strip()
        if not topic:
            raise CasePrepValidationError(
                "topic is required",
                details={"field": "topic"},
            )
        if self.max_per_category < 1:
            raise CasePrepValidationError(
                "max_per_category must be at least 1",
                details={"field": "max_per_category"},
            )
        object.__setattr__(self, "topic", topic)
        if self.output_dir is not None and not isinstance(self.output_dir, Path):
            object.__setattr__(self, "output_dir", Path(self.output_dir))
        if self.profile_hint is not None:
            object.__setattr__(self, "profile_hint", self.profile_hint.strip() or None)

    @classmethod
    def from_mapping(cls, values: dict[str, Any]) -> "BuildCasePlanRequest":
        return cls(
            topic=values["topic"],
            output_dir=values.get("output_dir") or None,
            max_per_category=values.get("max_per_category", 5),
            profile_hint=values.get("profile_hint"),
            structured_output=values.get("structured_output", False),
        )

    def default_output_dir(self) -> Path:
        return Path.cwd() / f"{_slugify_topic(self.topic)}-caseprep"

    def resolved_output_dir(self) -> Path:
        if self.output_dir is None:
            return self.default_output_dir()
        out = Path(self.output_dir)
        if not out.is_absolute():
            return Path.cwd() / out
        return out

    def to_legacy_args(self) -> dict[str, Any]:
        args: dict[str, Any] = {
            "topic": self.topic,
            "max_per_category": self.max_per_category,
        }
        if self.output_dir is not None:
            args["output_dir"] = str(self.output_dir)
        if self.profile_hint is not None:
            args["profile_hint"] = self.profile_hint
        return args


@dataclass(frozen=True)
class EvidenceRecord:
    """Normalized evidence item consumed by synthesis and provenance."""

    id: str
    source: str
    title: str = ""
    url: str | None = None
    text: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "source": self.source,
            "title": self.title,
            "url": self.url,
            "text": self.text,
            "metadata": self.metadata,
        }


@dataclass(frozen=True)
class ProvenanceRecord:
    """Field-level provenance for generated structured output."""

    field_path: str
    source_ids: list[str] = field(default_factory=list)
    value_status: str = "generated"
    generated_by: str = "caseprep"
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "field_path": self.field_path,
            "source_ids": self.source_ids,
            "value_status": self.value_status,
            "generated_by": self.generated_by,
            "notes": self.notes,
        }


@dataclass(frozen=True)
class ArtifactRef:
    """Reference to an artifact produced by a CasePrep run."""

    path: Path
    kind: str
    media_type: str | None = None
    label: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": str(self.path),
            "kind": self.kind,
            "media_type": self.media_type,
            "label": self.label,
            "metadata": self.metadata,
        }


@dataclass(frozen=True)
class BuildCasePlanResult:
    """Transport-neutral result for a built case plan."""

    topic: str
    markdown: str
    output_dir: Path | None = None
    mode: CoreMode = "legacy"
    artifacts: list[ArtifactRef] = field(default_factory=list)
    evidence: list[EvidenceRecord] = field(default_factory=list)
    provenance: list[ProvenanceRecord] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    structured: dict[str, Any] = field(default_factory=dict)
    shadow: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "topic": self.topic,
            "markdown": self.markdown,
            "output_dir": str(self.output_dir) if self.output_dir else None,
            "mode": self.mode,
            "artifacts": [artifact.to_dict() for artifact in self.artifacts],
            "evidence": [record.to_dict() for record in self.evidence],
            "provenance": [record.to_dict() for record in self.provenance],
            "warnings": self.warnings,
            "structured": self.structured,
            "shadow": self.shadow,
        }
