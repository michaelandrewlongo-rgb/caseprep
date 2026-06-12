"""Render a CompiledBoard (+ optional ranked figures) to a PDF ArtifactRef.

fpdf2 core fonts are latin-1; non-latin glyphs are mapped in _san(). Figures
are (path, caption) tuples keyed by section heading; each is embedded at a
legible width below its section with an italic caption.
"""

from __future__ import annotations

from pathlib import Path
from typing import Mapping, Sequence

from fpdf import FPDF

from caseprep.core.contracts import ArtifactRef

_REPL = {
    "≥": ">=",
    "≤": "<=",
    "×": "x",
    "→": "->",
    "—": "-",
    "–": "-",
    "“": '"',
    "”": '"',
    "‘": "'",
    "’": "'",
    "•": "-",
    "⚠": "[!]",
}


def _san(s: str) -> str:
    for k, v in _REPL.items():
        s = s.replace(k, v)
    return s.encode("latin-1", "replace").decode("latin-1")


def _render_figures(pdf: FPDF, items: Sequence) -> None:
    for path, caption in items:
        if pdf.get_y() + 90 > pdf.h - pdf.b_margin:
            pdf.add_page()
        pdf.image(str(path), w=min(pdf.epw, 120))
        pdf.set_font("Helvetica", "I", 8)
        pdf.set_text_color(90)
        pdf.multi_cell(0, 4, _san(caption), new_x="LMARGIN", new_y="NEXT")
        pdf.set_text_color(0)
        pdf.ln(2)


def board_to_pdf(
    board,
    out_path,
    *,
    figures: Mapping[str, Sequence] | None = None,
) -> ArtifactRef:
    figures = figures or {}
    pdf = FPDF(format="A4")
    pdf.set_auto_page_break(True, margin=18)
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 18)
    pdf.multi_cell(0, 9, _san(board.title), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)
    rendered_groups = set()
    for sec in board.sections:
        if not getattr(sec, "is_primary", True):
            continue
        pdf.set_font("Helvetica", "B", 13)
        band = f"  [{sec.confidence_band}]" if getattr(sec, "confidence_band", "") else ""
        pdf.multi_cell(0, 7, _san(sec.heading + band), new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "", 10)
        pdf.multi_cell(0, 5, _san(sec.body.strip()), new_x="LMARGIN", new_y="NEXT")
        pdf.ln(1)
        if sec.heading in figures:
            rendered_groups.add(sec.heading)
            _render_figures(pdf, figures[sec.heading])
    # Figure groups keyed by a heading the board doesn't have (e.g. the
    # "Evidence" fallback) still belong in the dossier — render them at the
    # end under their group name rather than dropping them silently.
    for group, items in figures.items():
        if group in rendered_groups or not items:
            continue
        pdf.set_font("Helvetica", "B", 13)
        pdf.multi_cell(0, 7, _san(f"Figures — {group}"),
                       new_x="LMARGIN", new_y="NEXT")
        pdf.ln(1)
        _render_figures(pdf, items)
    out_path = Path(out_path)
    pdf.output(str(out_path))
    return ArtifactRef(
        path=out_path,
        kind="pdf",
        media_type="application/pdf",
        label=board.title,
        metadata={"sections": len(board.sections)},
    )


def export_board_pdf(board, evidence, output_dir) -> ArtifactRef:
    """Render the compiled board plus the figure-bearing textbook evidence
    to ``<output_dir>/case-prep.pdf``."""
    from caseprep.export.figure_select import figures_for_sections

    figures = figures_for_sections(evidence)
    return board_to_pdf(board, Path(output_dir) / "case-prep.pdf",
                        figures=figures)
