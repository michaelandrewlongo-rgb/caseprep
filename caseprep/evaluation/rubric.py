"""Deterministic rubric for evaluating generated canonical CasePrep dossiers."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from caseprep.evaluation.canonical_cases import CanonicalCase

try:
    import yaml  # type: ignore
except ImportError:  # pragma: no cover - depends on optional dependency availability
    yaml = None  # type: ignore[assignment]


@dataclass(frozen=True)
class EvalReport:
    """Result from deterministic canonical dossier checks."""

    case_id: str
    passed: bool
    score: int | None
    missing_required_concepts: tuple[str, ...]
    deterministic_failures: tuple[str, ...]
    degradation_status: str | None
    output_dir: str | None


MAJOR_MARKDOWN_FILES = (
    "README.md",
    "01-case-summary.md",
    "02-imaging-review.md",
    "03-anatomy-at-risk.md",
    "04-operative-plan.md",
    "05-risk-and-rescue.md",
    "06-postop-plan.md",
    "07-evidence.md",
)

PLACEHOLDER_PATTERNS = (
    re.compile(r"\b(?:TODO|TBD)\b", re.IGNORECASE),
    re.compile(r"\{\{.*?\}\}"),
    re.compile(r"\bfill\s+in\b", re.IGNORECASE),
    re.compile(r"\[\s*insert[^\]]*\]", re.IGNORECASE),
    re.compile(r"<\s*(?:placeholder|fill[- ]?in|todo)\s*>", re.IGNORECASE),
    re.compile(r"_{3,}"),
)

# TODO: call project numeric guardrail when exposed as a reusable pure function.

_CONCEPT_ALIASES: dict[str, tuple[str, ...]] = {
    "discectomy/decompression": ("discectomy", "decompression"),
    "foraminal/uncinate": ("foraminal", "uncinate"),
    "graft/cage/plate": ("graft", "cage", "plate"),
    "sinus invasion/abutment": ("sinus invasion", "sinus abutment", "abutment"),
    "cortical/bridging veins": ("cortical veins", "bridging veins", "cortical vein", "bridging vein"),
    "debulking vs extracapsular dissection": (
        "debulking",
        "extracapsular dissection",
        "capsular dissection",
    ),
    "observation/SRS": ("observation", "SRS", "stereotactic radiosurgery"),
    "bone-only vs duraplasty": ("bone-only", "bone only", "duraplasty"),
    "CSF leak": ("CSF leak", "cerebrospinal fluid leak"),
    "M1/M2 anatomy": ("M1", "M2", "middle cerebral artery"),
    "lenticulostriate/perforator": ("lenticulostriate", "perforator"),
    "femoral/radial access": ("femoral access", "radial access", "transfemoral", "transradial"),
    "guide catheter/balloon guide/distal access catheter": (
        "guide catheter",
        "balloon guide",
        "distal access catheter",
    ),
    "aspiration vs stent retriever vs combined technique": (
        "aspiration",
        "stent retriever",
        "combined technique",
    ),
    "TICI/mTICI": ("TICI", "mTICI"),
    "time window/imaging selection": ("time window", "imaging selection", "last known well"),
    "symptomatic ICH": ("symptomatic ICH", "symptomatic intracranial hemorrhage"),
    "IV thrombolysis": ("IV thrombolysis", "intravenous thrombolysis", "tPA", "tenecteplase"),
    "rescue angioplasty/stenting": ("rescue angioplasty", "stenting", "angioplasty"),
}


def evaluate_case_output(output_dir: Path, canonical_case: CanonicalCase) -> EvalReport:
    """Run deterministic output checks for a generated dossier."""

    output_dir = Path(output_dir)
    failures: list[str] = []
    schema = _load_schema(output_dir / "caseprep.yaml")
    markdown_text = _read_markdown_text(output_dir)
    all_text = "\n".join([json.dumps(schema, sort_keys=True), markdown_text])

    if not output_dir.exists():
        failures.append(f"output directory does not exist: {output_dir}")
    if not (output_dir / "caseprep.yaml").exists():
        failures.append("missing caseprep.yaml")
    if not markdown_text.strip():
        failures.append("no markdown output files found")

    placeholder_failures = _placeholder_failures(output_dir)
    failures.extend(placeholder_failures)

    family = _parsed_family(schema, markdown_text)
    if canonical_case.expected_family and family != canonical_case.expected_family:
        failures.append(
            f"parsed family mismatch: expected {canonical_case.expected_family!r}, got {family!r}"
        )

    degradation_status = _degradation_status(schema, markdown_text)
    if canonical_case.degraded:
        if degradation_status != "degraded":
            failures.append("degraded case is not labeled degraded")
        if not _missing_facts_present(schema, markdown_text, require_nonempty=True):
            failures.append("degraded case does not expose missing critical facts")
    else:
        if not _evidence_table_nonempty(schema, output_dir):
            failures.append("evidence table is empty or placeholder-only")
        if not _missing_facts_present(schema, markdown_text, require_nonempty=False):
            failures.append("missing critical facts section is absent")

    missing_concepts = _missing_concepts(all_text, canonical_case.required_concepts)
    for concept in missing_concepts:
        failures.append(f"required concept missing: {concept}")

    score = max(0, 100 - 10 * len(failures))
    return EvalReport(
        case_id=canonical_case.id,
        passed=not failures,
        score=score,
        missing_required_concepts=tuple(missing_concepts),
        deterministic_failures=tuple(failures),
        degradation_status=degradation_status,
        output_dir=str(output_dir),
    )


def _load_schema(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8")
    try:
        if yaml is not None:
            loaded = yaml.safe_load(text) or {}
            return loaded if isinstance(loaded, dict) else {}

        try:
            loaded = json.loads(text)
        except json.JSONDecodeError:
            loaded = _minimal_yaml_parse(text)
        return loaded if isinstance(loaded, dict) else {}
    except Exception:
        return {}


def _minimal_yaml_parse(text: str) -> dict[str, Any]:
    """Small YAML fallback for project-generated caseprep.yaml files.

    This intentionally supports only the deterministic subset emitted by the
    project: indentation-based nested dictionaries, lists of scalars, and lists
    of dictionaries with simple scalar values. It is not a general YAML parser.
    """

    lines: list[tuple[int, str]] = []
    for raw_line in text.splitlines():
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(raw_line) - len(raw_line.lstrip(" "))
        lines.append((indent, stripped))

    def parse_block(index: int, indent: int) -> tuple[Any, int]:
        if index >= len(lines) or lines[index][0] < indent:
            return {}, index
        if lines[index][0] == indent and _is_list_item(lines[index][1]):
            return parse_list(index, indent)
        return parse_dict(index, indent)

    def parse_dict(index: int, indent: int) -> tuple[dict[str, Any], int]:
        result: dict[str, Any] = {}
        while index < len(lines):
            line_indent, content = lines[index]
            if line_indent < indent:
                break
            if line_indent > indent:
                index += 1
                continue
            if _is_list_item(content) or ":" not in content:
                break
            key, raw_value = content.split(":", 1)
            key = key.strip()
            raw_value = raw_value.strip()
            index += 1
            if raw_value:
                result[key] = _parse_scalar(raw_value)
            elif index < len(lines) and lines[index][0] > line_indent:
                result[key], index = parse_block(index, lines[index][0])
            else:
                result[key] = {}
        return result, index

    def parse_list(index: int, indent: int) -> tuple[list[Any], int]:
        result: list[Any] = []
        while index < len(lines):
            line_indent, content = lines[index]
            if line_indent < indent:
                break
            if line_indent > indent:
                index += 1
                continue
            if not _is_list_item(content):
                break
            item_text = content[1:].strip()
            index += 1
            if not item_text:
                if index < len(lines) and lines[index][0] > line_indent:
                    item, index = parse_block(index, lines[index][0])
                else:
                    item = None
            elif ":" in item_text:
                key, raw_value = item_text.split(":", 1)
                item = {key.strip(): _parse_scalar(raw_value.strip()) if raw_value.strip() else {}}
                if not raw_value.strip() and index < len(lines) and lines[index][0] > line_indent:
                    item[key.strip()], index = parse_block(index, lines[index][0])
                if index < len(lines) and lines[index][0] > line_indent:
                    child, index = parse_block(index, lines[index][0])
                    if isinstance(child, dict):
                        item.update(child)
            else:
                item = _parse_scalar(item_text)
            result.append(item)
        return result, index

    parsed, _ = parse_block(0, lines[0][0] if lines else 0)
    return parsed if isinstance(parsed, dict) else {}


def _is_list_item(content: str) -> bool:
    return content == "-" or content.startswith("- ")


def _parse_scalar(value: str) -> Any:
    if value == "":
        return ""
    if value in {"true", "True"}:
        return True
    if value in {"false", "False"}:
        return False
    if value in {"null", "None"}:
        return None
    if value.startswith("["):
        if not value.endswith("]"):
            raise ValueError("malformed inline YAML list")
        inner = value[1:-1].strip()
        if not inner:
            return []
        return [_parse_scalar(part.strip()) for part in inner.split(",")]
    if value.startswith("{") and not value.endswith("}"):
        raise ValueError("malformed inline YAML mapping")
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]
    return value


def _read_markdown_text(output_dir: Path) -> str:
    if not output_dir.exists():
        return ""
    texts = []
    for path in sorted(output_dir.glob("*.md")):
        texts.append(path.read_text(encoding="utf-8"))
    return "\n".join(texts)


def _placeholder_failures(output_dir: Path) -> list[str]:
    failures: list[str] = []
    for filename in MAJOR_MARKDOWN_FILES:
        path = output_dir / filename
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        for pattern in PLACEHOLDER_PATTERNS:
            if pattern.search(text):
                failures.append(f"placeholder text remains in {filename}: {pattern.pattern}")
                break
    return failures


def _parsed_family(schema: dict[str, Any], markdown_text: str) -> str | None:
    procedure_family = schema.get("procedure_family")
    if isinstance(procedure_family, dict) and procedure_family.get("id"):
        return str(procedure_family["id"])
    structured_case = schema.get("structured_case")
    if isinstance(structured_case, dict):
        field = structured_case.get("procedure_family")
        if isinstance(field, dict) and field.get("value"):
            return str(field["value"])
    found = re.search(r"Procedure family:\s*.*?`([^`]+)`", markdown_text, re.IGNORECASE)
    if found:
        return found.group(1)
    return None


def _degradation_status(schema: dict[str, Any], markdown_text: str) -> str | None:
    structured_case = schema.get("structured_case")
    if isinstance(structured_case, dict) and structured_case.get("degraded") is not None:
        return "degraded" if bool(structured_case.get("degraded")) else "not degraded"
    if re.search(r"Degradation status:\s*degraded", markdown_text, re.IGNORECASE):
        return "degraded"
    if re.search(r"Degradation status:\s*not degraded", markdown_text, re.IGNORECASE):
        return "not degraded"
    return None


def _missing_facts_present(
    schema: dict[str, Any], markdown_text: str, *, require_nonempty: bool
) -> bool:
    structured_case = schema.get("structured_case")
    if isinstance(structured_case, dict) and "missing_critical_facts" in structured_case:
        facts = structured_case.get("missing_critical_facts") or []
        return bool(facts) if require_nonempty else True
    found = re.search(
        r"Missing critical facts:\s*(?P<body>.*?)(?:\n- Degradation status:|\n## |\Z)",
        markdown_text,
        re.IGNORECASE | re.DOTALL,
    )
    if not found:
        return False
    body = found.group("body").strip()
    if not require_nonempty:
        return True
    return bool(body) and "none identified" not in body.casefold()


def _evidence_table_nonempty(schema: dict[str, Any], output_dir: Path) -> bool:
    evidence = (((schema.get("case") or {}).get("evidence") or {}) if isinstance(schema.get("case"), dict) else {})
    key_sources = evidence.get("key_sources") if isinstance(evidence, dict) else None
    if isinstance(key_sources, list) and len(key_sources) > 0:
        return True
    evidence_file = output_dir / "07-evidence.md"
    if not evidence_file.exists():
        return False
    markdown_text = evidence_file.read_text(encoding="utf-8")
    rows = [line.strip() for line in markdown_text.splitlines() if line.strip().startswith("|")]
    data_rows = [
        row
        for row in rows
        if not re.match(r"\|\s*-", row)
        and " ID " not in row
        and " Source " not in row
        and "needs input" not in row.casefold()
        and not re.search(r"\b(?:TODO|TBD)\b", row, re.IGNORECASE)
    ]
    return bool(data_rows)


def _missing_concepts(text: str, concepts: tuple[str, ...]) -> list[str]:
    normalized_text = _normalize(text)
    return [concept for concept in concepts if not _concept_present(normalized_text, concept)]


def _concept_present(normalized_text: str, concept: str) -> bool:
    aliases = _CONCEPT_ALIASES.get(concept, ()) + (concept,)
    expanded_aliases = list(aliases)
    if "/" in concept:
        expanded_aliases.extend(part.strip() for part in concept.split("/") if part.strip())
    if " vs " in concept.casefold():
        expanded_aliases.extend(part.strip() for part in re.split(r"\s+vs\s+", concept, flags=re.IGNORECASE))
    for alias in expanded_aliases:
        if _normalize(alias) in normalized_text:
            return True
    return False


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", text.casefold())).strip()
