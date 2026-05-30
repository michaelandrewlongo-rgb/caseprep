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
