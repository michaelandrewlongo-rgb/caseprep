"""Fan a single query across several evidence lanes and merge the hits.

Used to enrich Explorer question cards from more than one source — e.g. the
semantic corpus AND the user's textbook library — so a card's high-yield
question is answered (and, for textbook hits, illustrated) even when one lane
is unavailable. Lanes are queried independently; a lane that raises is skipped
rather than failing the whole enrichment.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from caseprep.core import CasePrepError, EvidenceRecord


class CompositeRetriever:
    """Round-robin merge of several retrievers sharing the corpus protocol."""

    def __init__(self, retrievers: Sequence[Any]) -> None:
        self._lanes = [r for r in retrievers if r is not None]

    def any_lanes(self) -> bool:
        return bool(self._lanes)

    def retrieve(
        self,
        query: str,
        *,
        subdomain: str | None = None,
        top_n: int = 5,
    ) -> list[EvidenceRecord]:
        per_lane: list[list[EvidenceRecord]] = []
        for lane in self._lanes:
            try:
                per_lane.append(list(lane.retrieve(
                    query, subdomain=subdomain, top_n=top_n)))
            except CasePrepError:
                # One lane down (e.g. textbook CLI missing, corpus backend
                # offline) must not blank the card — let the others answer it.
                continue
        # Round-robin so no single lane starves the others before the cap.
        merged: list[EvidenceRecord] = []
        for column in range(max((len(lane) for lane in per_lane), default=0)):
            for lane in per_lane:
                if column < len(lane):
                    merged.append(lane[column])
        return merged[:top_n]
