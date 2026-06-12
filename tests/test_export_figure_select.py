"""figure_select: pick figure-bearing textbook evidence for PDF sections."""

from caseprep.core import EvidenceRecord
from caseprep.export.figure_select import figures_for_sections


def _rec(section=None, figure_path="/f/p0726.png", **meta):
    metadata = {
        "citation": "Benzel Spine, p.592",
        "caption": "Fig 69-3",
        **({"figure_path": figure_path} if figure_path else {}),
        **({"section": section} if section else {}),
        **meta,
    }
    return EvidenceRecord(
        id="textbook-Benzel-p726",
        source="textbook",
        title="Benzel p.592",
        text="corpectomy failure",
        metadata=metadata,
    )


def test_picks_figure_bearing_textbook_records():
    out = figures_for_sections([_rec(section="Operative Plan")])
    assert out["Operative Plan"][0][0] == "/f/p0726.png"
    assert "Benzel Spine, p.592" in out["Operative Plan"][0][1]
    assert "Fig 69-3" in out["Operative Plan"][0][1]


def test_records_without_section_group_under_evidence():
    out = figures_for_sections([_rec()])
    assert "/f/p0726.png" == out["Evidence"][0][0]


def test_ignores_records_without_figures():
    assert figures_for_sections([_rec(figure_path=None)]) == {}


def test_ignores_non_textbook_sources():
    rec = _rec(section="Operative Plan")
    object.__setattr__(rec, "source", "pubmed") if hasattr(rec, "__dataclass_fields__") else None
    non_textbook = EvidenceRecord(
        id="pmid-1", source="pubmed", title="t", text="x",
        metadata={"figure_path": "/f/x.png", "section": "Operative Plan"},
    )
    assert figures_for_sections([non_textbook]) == {}


def test_caps_figures_per_section():
    records = [_rec(section="Operative Plan", figure_path=f"/f/p{i}.png")
               for i in range(5)]
    out = figures_for_sections(records, max_per_section=2)
    assert len(out["Operative Plan"]) == 2
