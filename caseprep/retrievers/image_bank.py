"""Deterministic image-bank retriever: spec string → ranked bank images.

Matching is structured (modality hint + cluster prefilter) plus lexical
token-overlap — no embedding model — so every match is explainable via the
exact ``matched_tokens`` it scored on.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

THROMBECTOMY_CLUSTERS = frozenset({
    "stroke_thrombectomy",
    "carotid_cervical_vascular",
    "intracranial_atherosclerosis",
    "general_neurointerventional",
})

# Spec-keyword → bank modality. Tuned for thrombectomy specs (NCCT/CTA/DSA/CTP);
# parse_modality_hint returns the FIRST hint in reading order.
MODALITY_HINTS = {
    "ncct": "CT", "noncontrast": "CT", "non-contrast": "CT", "ct": "CT",
    "ctp": "CT", "perfusion": "CT",
    "cta": "CT_angiography",
    "dsa": "DSA/angiogram", "angiogram": "DSA/angiogram", "angio": "DSA/angiogram",
    "fluoroscopic": "DSA/angiogram", "fluoroscopy": "DSA/angiogram",
    "mri": "MRI", "dwi": "MRI", "adc": "MRI", "flair": "MRI",
    "mra": "MR_angiography",
}

SPEC_STOPWORDS = frozenset({
    "image", "images", "view", "views", "axial", "coronal", "sagittal",
    "show", "showing", "display", "displayed", "and", "or", "the", "a", "an",
    "of", "in", "for", "with", "if", "to", "from", "on", "map", "maps",
})

MIN_SCORE = 0.20
DEFAULT_TOP_K = 2

_TOKEN_RE = re.compile(r"[a-z0-9]+")


@dataclass
class ImageMatch:
    fig_id: str
    local_path: str
    caption: str
    pmcid: str
    pmid: str
    score: float
    matched_spec: str
    matched_tokens: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "fig_id": self.fig_id,
            "local_path": self.local_path,
            "caption": self.caption,
            "pmcid": self.pmcid,
            "pmid": self.pmid,
            "score": round(self.score, 4),
            "matched_spec": self.matched_spec,
            "matched_tokens": list(self.matched_tokens),
        }


def parse_modality_hint(spec: str) -> str | None:
    """Return the bank modality implied by a spec string, or None."""
    tokens = _TOKEN_RE.findall((spec or "").lower())
    for tok in tokens:
        if tok in MODALITY_HINTS:
            return MODALITY_HINTS[tok]
    return None


def spec_tokens(spec: str) -> set[str]:
    """Content tokens of a spec, minus stopwords."""
    raw = set(_TOKEN_RE.findall((spec or "").lower()))
    return {t for t in raw if t not in SPEC_STOPWORDS}


class ImageBankRetriever:
    """Rank curated bank images for a single image-spec string.

    Pure/deterministic: no network, no model. ``index`` is the list produced by
    ``ImageIndex.load()``; ``None`` (missing sidecar) yields ``[]`` so callers
    degrade gracefully, mirroring SemanticCorpusRetriever's contract.
    """

    def __init__(
        self,
        *,
        index: list[dict] | None,
        clusters: frozenset[str] = THROMBECTOMY_CLUSTERS,
        min_score: float = MIN_SCORE,
    ) -> None:
        self._index = index
        self._clusters = clusters
        self._min_score = min_score

    def retrieve(self, spec: str, *, top_k: int = DEFAULT_TOP_K) -> list[ImageMatch]:
        if not self._index:
            return []
        want_tokens = spec_tokens(spec)
        if not want_tokens:
            return []
        modality = parse_modality_hint(spec)

        # Cluster prefilter.
        pool = [r for r in self._index if r["cluster"] in self._clusters]
        # Modality prefilter (relax if it would empty the pool).
        if modality:
            narrowed = [r for r in pool if r["modality"] == modality]
            if narrowed:
                pool = narrowed

        scored: list[ImageMatch] = []
        for rec in pool:
            cand = set(rec["tokens"])
            overlap = want_tokens & cand
            if not overlap:
                continue
            score = len(overlap) / len(want_tokens)
            if score < self._min_score:
                continue
            scored.append(ImageMatch(
                fig_id=rec["fig_id"],
                local_path=rec["local_path"],
                caption=rec["caption"],
                pmcid=rec["pmcid"],
                pmid=rec["pmid"],
                score=score,
                matched_spec=spec,
                matched_tokens=sorted(overlap),
            ))

        # Rank: score desc, then surgical_usefulness desc, then fig_id for stability.
        usefulness = {r["fig_id"]: r["surgical_usefulness"] for r in pool}
        scored.sort(key=lambda m: (-m.score, -usefulness.get(m.fig_id, 0), m.fig_id))
        return scored[:top_k]


__all__ = [
    "ImageMatch", "parse_modality_hint", "spec_tokens",
    "THROMBECTOMY_CLUSTERS", "MIN_SCORE", "DEFAULT_TOP_K",
    "ImageBankRetriever",
]
