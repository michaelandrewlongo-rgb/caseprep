"""CASEPREP_TEXTBOOK flag and CoreRetrieverSet.textbook field."""

import pytest

from caseprep.core import CasePrepConfigurationError
from caseprep.retrievers import resolve_textbook_enabled


def test_textbook_flag_default_off():
    assert resolve_textbook_enabled({}) is False


def test_textbook_flag_on():
    assert resolve_textbook_enabled({"CASEPREP_TEXTBOOK": "1"}) is True


def test_textbook_flag_rejects_garbage():
    with pytest.raises(CasePrepConfigurationError):
        resolve_textbook_enabled({"CASEPREP_TEXTBOOK": "yes"})


def test_default_core_retrievers_has_textbook_field(monkeypatch):
    monkeypatch.delenv("CASEPREP_TEXTBOOK", raising=False)
    from caseprep.core.builder import default_core_retrievers

    retriever_set = default_core_retrievers()
    assert hasattr(retriever_set, "textbook")
    assert retriever_set.textbook is None  # flag off -> not constructed


def test_default_core_retrievers_builds_textbook_when_enabled(monkeypatch):
    monkeypatch.setenv("CASEPREP_TEXTBOOK", "1")
    from caseprep.core.builder import default_core_retrievers
    from caseprep.retrievers.textbook import TextbookRetriever

    retriever_set = default_core_retrievers()
    assert isinstance(retriever_set.textbook, TextbookRetriever)
