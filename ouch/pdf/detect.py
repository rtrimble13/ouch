"""Form-type classification by signature scoring (spec §11.4).

Ambiguous classification is reported as such rather than guessed (P5).
"""

from __future__ import annotations

from dataclasses import dataclass

from ouch.pdf.maps_loader import FormMap

MIN_SCORE = 0.5
AMBIGUITY_MARGIN = 0.25


@dataclass(frozen=True)
class Detection:
    form: FormMap | None
    score: float
    ambiguous_with: str | None = None


def detect(text: str, maps: list[FormMap]) -> Detection:
    """Score the document text against each form's signature set."""
    lowered = text.lower()
    scored: list[tuple[float, FormMap]] = []
    for form_map in maps:
        hits = sum(1 for sig in form_map.signatures
                   if sig.lower() in lowered)
        score = hits / len(form_map.signatures) if form_map.signatures else 0.0
        scored.append((score, form_map))
    scored.sort(key=lambda pair: pair[0], reverse=True)

    best_score, best = scored[0]
    if best_score < MIN_SCORE:
        return Detection(form=None, score=best_score)
    if len(scored) > 1:
        second_score, second = scored[1]
        if second_score >= MIN_SCORE and best_score - second_score < AMBIGUITY_MARGIN:
            return Detection(form=best, score=best_score,
                             ambiguous_with=second.form)
    return Detection(form=best, score=best_score)
