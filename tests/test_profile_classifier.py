"""Tests for deterministic topic-to-profile classification."""

from __future__ import annotations

import builtins
import json
from pathlib import Path

import pytest

from caseprep.profile_classifier import (
    BASE_ANATOMY_KEYWORDS,
    BASE_APPROACH_KEYWORDS,
    BASE_COMPLICATION_KEYWORDS,
    build_keywords,
    classify_profile,
)


@pytest.mark.parametrize(
    "case",
    json.loads(
        (Path(__file__).parent / "fixtures" / "profile_classifier_topics.json")
        .read_text(encoding="utf-8")
    ),
)
def test_fixture_topic_profile_mapping(case):
    result = classify_profile(case["topic"])

    assert result.profile == case["profile"]


def test_classify_profile_uses_explicit_profile_hint():
    result = classify_profile(
        "vestibular schwannoma",
        profile_hint="vascular",
    )

    assert result.profile == "vascular"
    assert result.confidence == 1.0
    assert result.matched_term == "vascular"
    assert result.source == "hint"


def test_classify_profile_detects_longest_topic_match():
    result = classify_profile("brain metastasis resection")

    assert result.profile == "supratentorial_tumor"
    assert result.matched_term == "brain metastasis"
    assert result.source == "substring"
    assert result.confidence > 0


def test_classify_profile_falls_back_deterministically():
    result = classify_profile("rare nonspecific neurosurgical topic")

    assert result.profile == "skull_base"
    assert result.confidence == 0.0
    assert result.matched_term is None
    assert result.source == "fallback"


def test_build_keywords_merges_base_and_profile_without_mutating_base_lists():
    anatomy_before = list(BASE_ANATOMY_KEYWORDS)

    keywords = build_keywords("skull_base")
    keywords["anatomy"].append("mutated")

    assert "nerve" in keywords["anatomy"]
    assert "cranial nerve" in keywords["anatomy"]
    assert BASE_ANATOMY_KEYWORDS == anatomy_before
    assert "mutated" not in BASE_ANATOMY_KEYWORDS


def test_unknown_profile_uses_base_keyword_lists():
    keywords = build_keywords("unknown")

    assert keywords["anatomy"] == BASE_ANATOMY_KEYWORDS
    assert keywords["approach"] == BASE_APPROACH_KEYWORDS
    assert keywords["complications"] == BASE_COMPLICATION_KEYWORDS


def test_classifier_is_pure_and_does_not_open_files_or_network(monkeypatch):
    def fail_open(*args, **kwargs):
        raise AssertionError("classifier should not open files")

    monkeypatch.setattr(builtins, "open", fail_open)

    result = classify_profile("aneurysm clipping")
    keywords = build_keywords(result.profile)

    assert result.profile == "vascular"
    assert "aneurysm" in keywords["anatomy"]


def test_mcp_profile_detection_compatibility_wrapper_accepts_hint():
    from caseprep.mcp_server import _detect_profile

    profile, confidence = _detect_profile(
        "vestibular schwannoma",
        profile_hint="vascular",
    )

    assert profile == "vascular"
    assert confidence == 1.0
