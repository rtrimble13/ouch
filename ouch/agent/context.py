"""Redaction and context assembly (spec §14.5, §14.7).

Names and identity are stripped or refused; the numbers needed for analysis
travel through tools, never as raw profile context.
"""

from __future__ import annotations

import copy
from typing import Any

from ouch.model.input import TaxInput

_IDENTITY_KEYS = {"name"}


def redact_profile(raw: dict) -> dict:
    """Strip identity fields from a raw profile dict, recursively."""
    def scrub(node: Any) -> Any:
        if isinstance(node, dict):
            return {k: scrub(v) for k, v in node.items()
                    if k not in _IDENTITY_KEYS}
        if isinstance(node, list):
            return [scrub(v) for v in node]
        return node
    return scrub(copy.deepcopy(raw))


def transmission_notice(settings, inp: TaxInput) -> str:
    """What will be sent, shown before the user confirms (spec §14.7)."""
    provider = settings.get("ai.provider", "anthropic")
    model = settings.get("ai.model", "(configured)")
    return (
        f"AI analysis will transmit the following to {provider} "
        f"(model: {model}):\n"
        "    • Your question and the computed tax result / line-item trace "
        "(amounts only)\n"
        "    • Profile field values the model requests through logged tools, "
        "REDACTED as follows:\n"
        "        names → removed · SSNs → never stored\n"
        f"        state/locality → retained ({inp.taxpayer.state or 'none'}"
        f"{' / ' + inp.taxpayer.locality if inp.taxpayer.locality else ''}) "
        "(needed for analysis)\n"
        "  Nothing is sent until you confirm."
    )


def system_prompt(inp: TaxInput, data_verified: bool) -> str:
    """The agent's system prompt (spec §14.5 requirements 1–7)."""
    status = inp.taxpayer.filing_status.value.replace("_", " ")
    place = inp.taxpayer.state or "no state"
    if inp.taxpayer.locality:
        place += f" / {inp.taxpayer.locality}"
    verified_note = ("verified" if data_verified
                     else "UNVERIFIED/projected — say so when figures matter")
    return f"""You are an experienced CPA advising an individual on personal tax
planning, working inside `ouch`, a deterministic tax estimation engine.
The client files {status} in {place} for tax year {inp.tax_year}.

Numerical discipline — the cardinal rule:
- NEVER state a dollar figure that was not returned by a tool in this
  conversation. If you need a number, call the tool. If no tool can produce
  it, say so plainly instead of estimating.
- The engine computes; you interpret. Do not do arithmetic yourself beyond
  quoting tool results — even simple sums must come from a tool (e.g. run a
  scenario rather than adding two numbers).

Citations:
- Attach the trace line id or taxdata key in square brackets to every claim
  that rests on a computed number, e.g. [fed.tax.preferential] or
  [taxdata: niit.threshold].
- Never invent an IRC section, revenue ruling, or court case. If unsure of a
  citation, describe the rule without a cite.

Uncertainty:
- The loaded tax data for {inp.tax_year} is {verified_note}.
- State the fidelity level when a module is approximate or heuristic (tool
  results include it). Distinguish settled law from positions requiring
  professional judgment.

Scope boundary:
- Decline to advise on evasion, hiding income, or aggressive positions, and
  say why. Recommend a licensed practitioner for filing decisions, audits,
  notices, and anything with legal exposure. You estimate and plan; you do
  not prepare or file returns.

Answer style: prioritized, concrete, and grounded — lead with what matters
most in dollars, cite line ids, and propose next actions the user can run
(e.g. `ouch withhold solve --target safe-harbor`)."""
