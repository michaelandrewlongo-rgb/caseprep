"""PDF exporter: CompiledBoard (+ figures) -> ArtifactRef."""

from pathlib import Path

from caseprep.compile.case_compiler import CompiledBoard, CompiledSection
from caseprep.core.contracts import ArtifactRef
from caseprep.export.pdf import board_to_pdf


def _png(tmp_path):
    from PIL import Image

    p = tmp_path / "fig.png"
    Image.new("RGB", (400, 520), "white").save(p)
    return str(p)


def test_board_to_pdf_writes_artifact(tmp_path):
    board = CompiledBoard(
        title="C5-6 Corpectomy",
        sections=[
            CompiledSection(
                heading="Operative Plan",
                body="Front-back C5/C6 corpectomy.",
                confidence_band="moderate",
                is_primary=True,
            )
        ],
    )
    figs = {"Operative Plan": [(_png(tmp_path), "Benzel p.592: construct")]}
    out = tmp_path / "case.pdf"
    art = board_to_pdf(board, out, figures=figs)
    assert isinstance(art, ArtifactRef)
    assert art.kind == "pdf"
    assert Path(art.path).exists()
    assert out.stat().st_size > 1000


def test_board_to_pdf_handles_no_figures(tmp_path):
    board = CompiledBoard(
        title="T",
        sections=[CompiledSection(heading="H", body="b", is_primary=True)],
    )
    art = board_to_pdf(board, tmp_path / "x.pdf", figures=None)
    assert Path(art.path).exists()


def test_board_to_pdf_sanitizes_non_latin_glyphs(tmp_path):
    board = CompiledBoard(
        title="Kyphosis ≥ 15° — anterior–posterior",
        sections=[
            CompiledSection(heading="Plan ⚠", body="Correct → fuse C4–T1.",
                            is_primary=True)
        ],
    )
    art = board_to_pdf(board, tmp_path / "g.pdf", figures=None)
    assert Path(art.path).exists()


def test_board_to_pdf_skips_appendix_sections(tmp_path):
    board = CompiledBoard(
        title="T",
        sections=[
            CompiledSection(heading="Primary", body="p", is_primary=True),
            CompiledSection(heading="Appendix", body="a", is_primary=False),
        ],
    )
    art = board_to_pdf(board, tmp_path / "x.pdf", figures=None)
    assert art.metadata["sections"] == 2  # board sections counted
    assert Path(art.path).exists()


def test_unmatched_figure_groups_render_in_trailing_section(tmp_path):
    """Figures keyed by a heading absent from the board still land in the
    PDF (trailing group), instead of being silently dropped."""
    board = CompiledBoard(
        title="T",
        sections=[CompiledSection(heading="Operative Plan", body="b",
                                  is_primary=True)],
    )
    figs = {"Evidence": [(_png(tmp_path), "Benzel Spine, p.592 - Fig 69-3")]}
    with_figs = tmp_path / "with.pdf"
    without_figs = tmp_path / "without.pdf"
    board_to_pdf(board, with_figs, figures=figs)
    board_to_pdf(board, without_figs, figures=None)
    assert with_figs.stat().st_size > without_figs.stat().st_size + 500


def test_export_board_pdf_embeds_textbook_figures(tmp_path):
    from caseprep.core import EvidenceRecord
    from caseprep.export.pdf import export_board_pdf

    board = CompiledBoard(
        title="C5-6 Corpectomy",
        sections=[CompiledSection(heading="Operative Plan", body="plan",
                                  is_primary=True)],
    )
    evidence = [EvidenceRecord(
        id="textbook-Benzel-p726", source="textbook", title="Benzel p.592",
        text="corpectomy", metadata={"figure_path": _png(tmp_path),
                                     "citation": "Benzel Spine, p.592",
                                     "caption": "Fig 69-3"},
    )]
    art = export_board_pdf(board, evidence, tmp_path)
    assert art.kind == "pdf"
    assert Path(art.path).name == "case-prep.pdf"
    assert Path(art.path).exists()
    assert Path(art.path).stat().st_size > 1000
