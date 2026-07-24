"""`ouch harvest` — tax-loss harvesting: analysis, not execution (spec §13).

ouch never connects to a brokerage to trade.
"""

from __future__ import annotations

import datetime as _dt
from decimal import Decimal
from pathlib import Path
from typing import List, Optional

import typer

from ouch import DISCLAIMER
from ouch.cli.common import Runtime, load_data
from ouch.config import profile as profile_mod
from ouch.errors import UsageError
from ouch.harvest import lots as lots_mod
from ouch.harvest import ranker, washsale
from ouch.model.money import Money, ZERO

app = typer.Typer(no_args_is_help=True)


def _as_of(value: Optional[str]) -> _dt.date:
    if value is None:
        return _dt.date.today()
    try:
        return _dt.date.fromisoformat(value)
    except ValueError as e:
        raise UsageError(f"--as-of must be YYYY-MM-DD, got '{value}'") from e


def _context(rt: Runtime):
    from ouch.cli.common import _derive_periods_remaining
    raw, _ = profile_mod.load_profile_raw(rt.profile_name)
    _derive_periods_remaining(raw, _dt.date.today(), rt.tax_year)
    build = lambda r: profile_mod.build_tax_input(r, rt.tax_year)  # noqa: E731
    data = load_data(build(raw))
    return raw, build, data


@app.command("import")
def import_lots(ctx: typer.Context,
                file: Path = typer.Argument(..., help="Canonical lot CSV")) -> None:
    """Validate a lot CSV and install it as the portfolio."""
    rt: Runtime = ctx.obj
    parsed = lots_mod.parse_lots_csv(file)
    ira = sum(1 for lot in parsed if lot.is_ira)
    if rt.dry_run:
        rt.console().print(f"✔ {len(parsed)} lots valid ({ira} in IRA "
                           "accounts) — --dry-run, nothing written")
        return
    target = lots_mod.save_portfolio(parsed)
    rt.console().print(
        f"✔ {len(parsed)} lots imported to {target}"
        + (f"\n  ℹ {ira} IRA lot(s) will be excluded from harvesting — a "
           "loss there has no tax value" if ira else ""))


@app.command("scan")
def scan(ctx: typer.Context,
         as_of: Optional[str] = typer.Option(None, "--as-of",
                                             help="Hypothetical sale date "
                                                  "[default: today]"),
         min_benefit: float = typer.Option(0, "--min-benefit",
                                           help="Hide candidates below this "
                                                "tax benefit")) -> None:
    """Rank positions whose realization would reduce current-year tax."""
    rt: Runtime = ctx.obj
    console = rt.console()
    sale_date = _as_of(as_of)
    portfolio = lots_mod.load_portfolio()
    raw, build, data = _context(rt)

    baseline = ranker._run(raw, data, build)
    rates = ranker.marginal_gain_rates(raw, data, build, baseline=baseline)
    candidates, excluded = ranker.scan(
        portfolio, raw, data, build, as_of=sale_date,
        min_benefit=Money(str(min_benefit)))

    n_accounts = len({lot.account for lot in portfolio})
    console.print(f"Portfolio: {len(portfolio)} lots · {n_accounts} "
                  f"account(s) · as of {sale_date}")
    console.print(f"Harvest candidates · marginal ST "
                  f"{rates.short_term * 100:.2f}% / LT "
                  f"{rates.long_term * 100:.2f}% (combined, computed "
                  "numerically)\n")
    if not candidates:
        console.print("  no harvestable losses above the threshold")
    else:
        console.print(f"  {'#':>3} {'Symbol':<7} {'Lot':<10} {'Char':<6}"
                      f"{'Unrealized':>13} {'Tax benefit':>13}  Wash risk")
        for i, c in enumerate(candidates, 1):
            if c.wash.clear:
                risk = "✔ clear"
            elif c.wash.permanent:
                risk = "✖ IRA purchase in window — loss PERMANENTLY disallowed"
            else:
                risk = (f"⚠ {c.wash.disallowed_shares} sh repurchased in "
                        f"window — ${c.wash.disallowed_loss.round_dollar().amount:,.0f} disallowed")
            console.print(f"  {i:>3} {c.lot.symbol:<7} {c.lot.lot_id:<10} "
                          f"{c.character:<6}{c.unrealized.fmt():>13} "
                          f"{c.tax_benefit.fmt():>13}  {risk}")
    for c in excluded:
        console.print(f"      {c.lot.symbol} {c.lot.lot_id}: excluded — "
                      f"{c.excluded_reason}")

    room = ranker.zero_band_room(baseline, data,
                                 build(raw).taxpayer.filing_status)
    if room > ZERO:
        console.print(f"\n  ℹ Gain harvesting: {room.fmt()} of room remains "
                      "in the 0% preferential band — long-term gains "
                      "realized up to that amount are taxed at 0% federally.")
    alerts = ranker.holding_period_alerts(portfolio, sale_date)
    for lot, days in alerts:
        console.print(f"  ⚠ {lot.symbol} {lot.lot_id}: gain lot crosses the "
                      f"long-term boundary in {days} days — waiting changes "
                      "the rate from short-term to long-term.")
    console.print("\n  Substantially-identical analysis covers exact symbol "
                  "matches only (fidelity: approximate).")
    console.print(f"\n[dim]{DISCLAIMER.splitlines()[0]}[/dim]")


@app.command("simulate")
def simulate(ctx: typer.Context,
             sell: List[str] = typer.Option(..., "--sell",
                                            help="Lot id(s) to sell, repeatable"),
             as_of: Optional[str] = typer.Option(None, "--as-of"),
             future_rate: Optional[float] = typer.Option(
                 None, "--future-rate",
                 help="Assumed rate on the deferred gain "
                      "[default: current marginal LTCG rate]"),
             discount_rate: float = typer.Option(0.05, "--discount-rate"),
             horizon: int = typer.Option(10, "--horizon",
                                         help="Years until the deferred gain "
                                              "is realized")) -> None:
    """Simulate selling specific lots through the full pipeline."""
    rt: Runtime = ctx.obj
    console = rt.console()
    sale_date = _as_of(as_of)
    portfolio = lots_mod.load_portfolio()
    raw, build, data = _context(rt)

    sim = ranker.simulate(
        sell, portfolio, raw, data, build, as_of=sale_date,
        future_rate=None if future_rate is None else Decimal(str(future_rate)),
        discount_rate=Decimal(str(discount_rate)), horizon_years=horizon)

    console.print(f"Simulated sale of {len(sim.lots_sold)} lot(s) on "
                  f"{sale_date}\n")
    console.print(f"  Short-term realized                   "
                  f"{sim.netting.st_realized.fmt():>12}")
    console.print(f"  Long-term realized                    "
                  f"{sim.netting.lt_realized.fmt():>12}")
    if sim.netting.ordinary_offset < ZERO:
        console.print(f"  Loss applied against ordinary income  "
                      f"{sim.netting.ordinary_offset.fmt():>12}   (limited)")
    if sim.netting.carryforward_st + sim.netting.carryforward_lt > ZERO:
        console.print(f"  Carryforward to {sim.before.year + 1}                 "
                      f"    ST {sim.netting.carryforward_st.fmt()} · "
                      f"LT {sim.netting.carryforward_lt.fmt()}   "
                      "(character preserved)")

    console.print("\n  Tax effect:")
    console.print(f"    {'':<24}{'Before':>12}{'After':>12}{'Δ':>12}")
    rows = [("Federal", sim.before.federal_total_tax,
             sim.after.federal_total_tax)]
    if sim.before.state is not None:
        rows.append((f"State ({sim.before.state.code})", sim.before.state.tax,
                     sim.after.state.tax if sim.after.state else ZERO))
    if sim.before.local is not None:
        rows.append((f"Local ({sim.before.local.name})", sim.before.local.tax,
                     sim.after.local.tax if sim.after.local else ZERO))
    rows.append(("Total tax", sim.before.total_tax_all_jurisdictions,
                 sim.after.total_tax_all_jurisdictions))
    for label, before, after in rows:
        delta = after - before
        console.print(f"    {label:<24}{before.fmt():>12}{after.fmt():>12}"
                      f"{delta.fmt():>12}")

    console.print("\n  Deferred cost (harvesting is largely a deferral):")
    console.print(f"    Basis reduction                       "
                  f"{sim.basis_reduction.fmt():>12}")
    console.print(f"    Future tax at assumed "
                  f"{sim.future_rate * 100:.2f}%          "
                  f"{sim.future_tax_cost.fmt():>12}")
    console.print(f"    Net present benefit @ "
                  f"{sim.discount_rate * 100:.0f}% / {sim.horizon_years} yr    "
                  f"    {sim.npv_benefit.fmt():>12}")

    for risk in sim.wash_risks:
        if risk.permanent:
            console.print(f"\n  ✖ {risk.sale_lot.symbol} "
                          f"{risk.sale_lot.lot_id}: an IRA purchase inside "
                          "the ±30-day window PERMANENTLY disallows "
                          f"${risk.disallowed_loss.round_dollar().amount:,.0f} "
                          "of the loss — the basis adjustment has nowhere "
                          "to go.")
        elif not risk.clear:
            console.print(f"\n  ⚠ {risk.sale_lot.symbol} "
                          f"{risk.sale_lot.lot_id}: {risk.disallowed_shares} "
                          "share(s) repurchased inside the window — "
                          f"${risk.disallowed_loss.round_dollar().amount:,.0f} "
                          "of the loss would be disallowed. The pipeline "
                          "figures above assume the FULL loss; clear the "
                          "window first.")
    end = sale_date + _dt.timedelta(days=washsale.WINDOW_DAYS + 1)
    console.print(f"\n  ⚠ Do not repurchase these securities before {end} "
                  "(and turn off dividend reinvestment).")
    console.print(f"\n[dim]{DISCLAIMER.splitlines()[0]}[/dim]")


@app.command("washsale-check")
def washsale_check(ctx: typer.Context,
                   as_of: Optional[str] = typer.Option(None, "--as-of")) -> None:
    """Wash-sale exposure for every loss lot in the portfolio."""
    rt: Runtime = ctx.obj
    console = rt.console()
    sale_date = _as_of(as_of)
    portfolio = lots_mod.load_portfolio()
    any_risk = False
    for lot in portfolio:
        if lot.unrealized >= ZERO or lot.is_ira:
            continue
        risk = washsale.check(lot, portfolio, sale_date)
        if risk.clear:
            continue
        any_risk = True
        for c in risk.conflicts:
            where = " (IRA — permanent)" if c.permanent else ""
            console.print(f"  ⚠ {lot.symbol} {lot.lot_id}: {c.shares} sh "
                          f"purchased {c.lot.acquired_date} in "
                          f"{c.lot.account}{where} — "
                          f"${risk.disallowed_loss.round_dollar().amount:,.0f} "
                          "of the loss disallowed if sold "
                          f"{sale_date}")
    if not any_risk:
        console.print(f"  ✔ no wash-sale conflicts for sales on {sale_date} "
                      "(exact-symbol matches only)")
