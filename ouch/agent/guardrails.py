"""Guardrails: post-processing validation on every response (spec §14.6).

| Check                                   | Action on failure              |
| Numeric grounding ($ figures vs tools)  | Retry once, then refuse        |
| Citation presence on numeric claims     | Append "uncited" marker        |
| Scope (evasion/fraud)                   | Hard refusal, logged           |
| Disclaimer present                      | Injected unconditionally       |
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal

# Figures below this are treated as conversational ("$0", "$5") rather than
# computed results; everything above must trace to a tool value.
GROUNDING_FLOOR = Decimal(100)
GROUNDING_TOLERANCE = Decimal(1)

_DOLLAR = re.compile(r"\$\s?([\d,]+(?:\.\d+)?)(\s?[kKmM]\b)?")
_CITE = re.compile(r"\[[\w .:$/§-]+\]")

# Requests ouch will not help with (spec §14.5 item 5, §14.6). Deliberately a
# narrow, high-precision list — the system prompt carries the broader policy.
_SCOPE_PATTERNS = [
    r"\bhide\b.{0,40}\b(income|money|assets|cash)\b",
    r"\b(income|money|cash|tips)\b.{0,40}\bwithout (reporting|declaring)\b",
    r"\bnot\s+report(ing)?\b.{0,40}\b(income|cash|tips|1099|w-?2)\b",
    r"\bunder the table\b",
    r"\boff the books\b",
    r"\bevade\b.{0,20}\btax",
    r"\btax evasion\b",
    r"\bfake\b.{0,20}\b(deduction|receipt|dependent|expense)s?\b",
    r"\bdon'?t tell the irs\b",
    r"\blaunder",
]


@dataclass(frozen=True)
class ScopeVerdict:
    allowed: bool
    reason: str = ""


def scope_check(question: str) -> ScopeVerdict:
    lowered = question.lower()
    for pattern in _SCOPE_PATTERNS:
        if re.search(pattern, lowered):
            return ScopeVerdict(
                allowed=False,
                reason="This looks like a request to conceal income or "
                       "evade tax, which ouch will not help with. Tax "
                       "*avoidance* through legal planning is fine — ask "
                       "about deductions, deferral, timing, or credits.")
    return ScopeVerdict(allowed=True)


def extract_dollar_figures(text: str) -> list[Decimal]:
    figures = []
    for m in _DOLLAR.finditer(text):
        value = Decimal(m.group(1).replace(",", ""))
        suffix = (m.group(2) or "").strip().lower()
        if suffix == "k":
            value *= 1000
        elif suffix == "m":
            value *= 1_000_000
        figures.append(value)
    return figures


def ungrounded_figures(text: str, registry: set[Decimal]) -> list[Decimal]:
    """Figures in the text that match no tool-returned number within
    rounding. The cardinal rule's enforcement point."""
    bad = []
    for figure in extract_dollar_figures(text):
        if figure < GROUNDING_FLOOR:
            continue
        quantized = figure.quantize(Decimal("0.01"))
        if any(abs(quantized - n) <= GROUNDING_TOLERANCE for n in registry):
            continue
        bad.append(figure)
    return bad


def has_citations(text: str) -> bool:
    return bool(_CITE.search(text))


def annotate(text: str, registry: set[Decimal]) -> tuple[str, list[str]]:
    """Final annotation pass. Returns (text, warnings). Grounding failures
    are handled upstream (retry-then-refuse); this adds soft markers."""
    warnings = []
    if extract_dollar_figures(text) and not has_citations(text):
        warnings.append("response cites no line items — verify figures with "
                        "`ouch estimate --explain`")
    return text, warnings


CORRECTION_PROMPT = (
    "Your previous answer contained dollar figures that do not match any "
    "tool result: {figures}. Every figure must come from a tool call. "
    "Re-answer using only numbers returned by tools — call more tools if "
    "you need more numbers."
)

REFUSAL_TEXT = (
    "I can't give you a grounded answer: the model produced figures that "
    "don't trace to the engine's computation, twice. No numbers were "
    "invented on your behalf — run `ouch estimate --explain` for the "
    "deterministic result, or re-ask a more specific question."
)
