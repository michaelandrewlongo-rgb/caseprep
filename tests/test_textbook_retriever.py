"""TextbookRetriever: normalize `textbook-rag search --json` hits."""

import pytest

from caseprep.core import CasePrepExternalServiceError, EvidenceRecord
from caseprep.retrievers.textbook import TextbookRetriever

FAKE = [
    {
        "book": "Benzel Spine",
        "chapter": "Cervical Spondylotic Myelopathy",
        "page": 726,
        "printed_page": "592",
        "text": "Anterior-only two-level corpectomy failure rates rise with levels.",
        "score": 0.91,
        "figure_path": "/figs/p0726.png",
        "caption": "Fig 69-3",
    }
]


def test_normalizes_to_evidence_records():
    retriever = TextbookRetriever(search_fn=lambda q, k: FAKE)
    records = retriever.retrieve("two level corpectomy failure", top_n=5)
    assert len(records) == 1
    record = records[0]
    assert isinstance(record, EvidenceRecord)
    assert record.source == "textbook"
    assert record.id == "textbook-Benzel Spine-p726"
    assert "corpectomy failure" in record.text
    assert record.metadata["printed_page"] == "592"
    assert record.metadata["figure_path"] == "/figs/p0726.png"
    assert record.metadata["citation"] == "Benzel Spine, p.592"


def test_citation_falls_back_to_pdf_index_when_no_folio():
    retriever = TextbookRetriever(
        search_fn=lambda q, k: [{**FAKE[0], "printed_page": None}]
    )
    record = retriever.retrieve("q")[0]
    assert record.metadata["citation"] == "Benzel Spine, PDF p.726"


def test_wraps_failure_as_external_service_error():
    def boom(q, k):
        raise RuntimeError("subprocess died")

    with pytest.raises(CasePrepExternalServiceError) as excinfo:
        TextbookRetriever(search_fn=boom).retrieve("q")
    assert excinfo.value.details.get("provider") == "textbook"


def test_skips_hits_missing_book_or_page():
    hits = [{**FAKE[0], "book": ""}, {**FAKE[0], "page": None}, FAKE[0]]
    records = TextbookRetriever(search_fn=lambda q, k: hits).retrieve("q")
    assert len(records) == 1


def test_respects_top_n():
    hits = [dict(FAKE[0], page=700 + i) for i in range(10)]
    records = TextbookRetriever(search_fn=lambda q, k: hits).retrieve("q", top_n=3)
    assert len(records) == 3
