"""Human-readable summary rendering (spec §8.3). Progressive disclosure:
verbosity 1 = one-screen summary, 2 = subtotals, 3 = full trace.
"""

from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from ouch import DISCLAIMER
from ouch.model.enums import FilingStatus
from ouch.model.money import Money, ZERO
from ouch.model.result import TaxResult

_STATUS_LABEL = {
    FilingStatus.SINGLE: "Single",
    FilingStatus.MARRIED_FILING_JOINTLY: "Married Filing Jointly",
    FilingStatus.MARRIED_FILING_SEPARATELY: "Married Filing Separately",
    FilingStatus.HEAD_OF_HOUSEHOLD: "Head of Household",
    FilingStatus.QUALIFYING_SURVIVING_SPOUSE: "Qualifying Surviving Spouse",
}


def _row(label: str, money: Money, *, indent: int = 0, sign: str = "") -> str:
    amount = money.fmt()
    pad = "  " * indent
    return f"{pad}{label:<44}{amount:>16}"


def render_summary(result: TaxResult, status: FilingStatus, state: str,
                   locality: str, *, verbosity: int = 1,
                   console: Console | None = None) -> None:
    console = console or Console()
    lines: list[str] = []

    lines.append(_row("Total income", result.total_income))
    lines.append(_row("Adjusted gross income", result.agi))
    lines.append(_row(f"Deduction ({result.deduction_mode})",
                      -result.deduction_taken))
    if result.nonitemizer_charitable_deduction > ZERO:
        lines.append(_row("Charitable (non-itemizer)",
                          -result.nonitemizer_charitable_deduction))
    if result.schedule_1a_deduction > ZERO:
        lines.append(_row("Schedule 1-A deductions",
                          -result.schedule_1a_deduction))
    if result.qbi_deduction > ZERO:
        lines.append(_row("QBI deduction", -result.qbi_deduction))
    lines.append(_row("Taxable income", result.taxable_income))
    lines.append("")
    lines.append(_row("Federal income tax",
                      result.tax_ordinary + result.tax_preferential))
    if verbosity >= 1:
        lines.append(_row("ordinary", result.tax_ordinary, indent=1))
        if result.tax_preferential > ZERO:
            lines.append(_row("preferential (QD + LTCG)",
                              result.tax_preferential, indent=1))
    if result.amt_additional > ZERO:
        lines.append(_row("Alternative minimum tax", result.amt_additional))
    if result.se_tax > ZERO:
        lines.append(_row("Self-employment tax", result.se_tax))
    if result.additional_medicare > ZERO:
        lines.append(_row("Additional Medicare tax", result.additional_medicare))
    if result.niit > ZERO:
        lines.append(_row("Net investment income tax", result.niit))
    credits = result.credits_nonrefundable + result.credits_refundable
    if credits > ZERO:
        lines.append(_row("Credits", -credits))
    lines.append("  " + "─" * 58)
    lines.append(_row("Federal total", result.federal_total_tax))
    if result.state is not None and (result.state.tax > ZERO or verbosity >= 2):
        lines.append(_row(f"{result.state.code} state tax", result.state.tax))
    if result.local is not None and result.local.tax > ZERO:
        lines.append(_row(f"{result.local.name} local tax", result.local.tax))
    if result.other_state is not None and result.other_state.tax > ZERO:
        lines.append(_row(f"{result.other_state.code} (part-year)",
                          result.other_state.tax))
    lines.append("  " + "═" * 58)
    lines.append(_row("TOTAL TAX BURDEN", result.total_tax_all_jurisdictions))
    lines.append("")
    lines.append(f"  {'Effective rate (of AGI)':<44}"
                 f"{result.effective_rate_agi * 100:>15.2f}%")
    lines.append(f"  {'Effective rate (of gross income)':<44}"
                 f"{result.effective_rate_gross * 100:>15.2f}%")
    if result.marginal_rate_combined:
        lines.append(f"  {'Marginal rate on next dollar (combined)':<44}"
                     f"{result.marginal_rate_combined * 100:>15.2f}%")
    lines.append("")
    lines.append(_row("Withheld + paid (projected through year end)",
                      result.total_payments))
    balance = result.balance_due_or_refund
    if balance >= ZERO:
        lines.append(_row("▸ PROJECTED BALANCE DUE", balance))
    else:
        lines.append(_row("▸ PROJECTED REFUND", -balance))

    if result.warnings:
        lines.append("")
        for w in result.warnings:
            lines.append(f"  ⚠  {w}")

    place = state or "no state"
    if locality:
        place += f" / {locality}"
    title = (f"ouch · Tax Year {result.year} · {_STATUS_LABEL[status]} · {place}"
             f" · fidelity: {result.fidelity}")
    console.print(Panel(Text("\n".join(lines)), title=title, expand=False))
    console.print(f"  {DISCLAIMER.splitlines()[0]} "
                  "Run `ouch --explain estimate` for detail.", style="dim")
