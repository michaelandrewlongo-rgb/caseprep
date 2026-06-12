"""CompositeRetriever: fan a card query across several evidence lanes."""

from caseprep.core import CasePrepExternalServiceError, EvidenceRecord
from caseprep.retrievers.composite import CompositeRetriever


def _rec(rid, source):
    return EvidenceRecord(id=rid, source=source, title=rid, text="t",
                          metadata={"retrieval_source": source})


class FakeLane:
    def __init__(self, recs, *, boom=False):
        self._recs = recs
        self._boom = boom
        self.calls = []

    def retrieve(self, query, *, subdomain=None, top_n=5):
        self.calls.append((query, subdomain, top_n))
        if self._boom:
            raise CasePrepExternalServiceError("lane down",
                                               details={"provider": "x"})
        return list(self._recs)


def test_interleaves_lanes_and_caps_at_top_n():
    sem = FakeLane([_rec("s1", "corpus_semantic"), _rec("s2", "corpus_semantic")])
    book = FakeLane([_rec("b1", "textbook"), _rec("b2", "textbook")])
    out = CompositeRetriever([sem, book]).retrieve("q", top_n=3)
    assert [r.id for r in out] == ["s1", "b1", "s2"]  # round-robin, capped at 3


def test_one_lane_failing_does_not_kill_the_other():
    sem = FakeLane([], boom=True)
    book = FakeLane([_rec("b1", "textbook")])
    out = CompositeRetriever([sem, book]).retrieve("q", top_n=3)
    assert [r.id for r in out] == ["b1"]


def test_none_lanes_filtered_and_any_present():
    book = FakeLane([_rec("b1", "textbook")])
    composite = CompositeRetriever([None, book, None])
    assert composite.any_lanes() is True
    assert CompositeRetriever([None, None]).any_lanes() is False


def test_passes_top_n_to_each_lane():
    sem = FakeLane([_rec("s1", "corpus_semantic")])
    book = FakeLane([_rec("b1", "textbook")])
    CompositeRetriever([sem, book]).retrieve("q", top_n=4)
    assert sem.calls[0][2] == 4 and book.calls[0][2] == 4


def test_textbook_figure_metadata_survives_the_merge():
    book = FakeLane([EvidenceRecord(
        id="textbook-Benzel-p726", source="textbook", title="Benzel p.592",
        text="corpectomy", metadata={"figure_path": "/f/p0726.png",
                                     "citation": "Benzel Spine, p.592"})])
    out = CompositeRetriever([book]).retrieve("two level corpectomy", top_n=3)
    assert out[0].metadata["figure_path"] == "/f/p0726.png"
    assert out[0].metadata["citation"] == "Benzel Spine, p.592"
