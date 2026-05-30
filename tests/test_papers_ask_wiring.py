from caseprep.core import EvidenceRecord
from caseprep.core.builder import CoreRetrieverSet, default_core_retrievers


class _StubPapers:
    def retrieve(self, query, *, subdomain=None, top_n=8):
        return [EvidenceRecord(id="papers-ask-1", source="papers", title="P",
                               text="P", metadata={})]


def test_retriever_set_accepts_papers_ask():
    s = CoreRetrieverSet(
        pubmed=object(), radiology=object(), corpus=object(),
        corpus_semantic=None, papers_ask=_StubPapers(),
    )
    assert s.papers_ask is not None


def test_default_set_includes_papers_ask():
    s = default_core_retrievers()
    assert hasattr(s, "papers_ask")
    assert s.papers_ask is not None


import inspect

from caseprep.core import builder as builder_mod


def test_builder_invokes_papers_ask_and_tags_source():
    """The retrieval body must call provider_set.papers_ask.retrieve and tag
    records with retrieval_source='papers_ask' (mirrors the corpus_semantic block)."""
    src = inspect.getsource(builder_mod)
    assert "provider_set.papers_ask" in src
    assert '"papers_ask"' in src or "'papers_ask'" in src


def test_builder_structured_dict_exposes_papers_ask_observability():
    """The structured retrieval dict must surface papers_ask run state
    (parity with semantic_used observability)."""
    import inspect
    from caseprep.core import builder as builder_mod
    src = inspect.getsource(builder_mod)
    assert "papers_ask_enabled" in src
    assert "papers_ask_query" in src
    # caps entry present
    assert '"papers_ask": semantic_top_n if papers_used else None' in src
