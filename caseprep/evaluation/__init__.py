"""Canonical deterministic evaluation harness for CasePrep dossiers."""

from caseprep.evaluation.canonical_cases import (
    CanonicalCase,
    all_canonical_cases,
    degraded_cases,
    full_canonical_cases,
)
from caseprep.evaluation.rubric import EvalReport, evaluate_case_output

__all__ = [
    "CanonicalCase",
    "EvalReport",
    "all_canonical_cases",
    "degraded_cases",
    "evaluate_case_output",
    "full_canonical_cases",
]
