"""Harvest candidate scoring and simulation (spec §13.4–13.6).

The benefit of harvesting is *not* `loss × marginal_rate`. It is computed by
re-running the full pipeline:

    benefit = tax(baseline) − tax(baseline with realized loss)

which automatically accounts for the ordinary-offset limit, character
matching, NIIT, and state treatment. The deferred cost (basis reduction) is
always reported alongside — harvesting is largely a deferral.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Callable

from ouch.engine import pipeline
from ouch.engine.income import net_capital
from ouch.engine.pipeline import ResolvedData
from ouch.errors import UsageError
from ouch.harvest import washsale
from ouch.model.enums import FilingStatus
from ouch.model.input import TaxInput
from ouch.model.money import Money, ZERO, maxm, minm
from ouch.model.portfolio import Lot
from ouch.model.result import TaxResult
from ouch.scenario.model import get_path, set_path

BuildInput = Callable[[dict], TaxInput]


def with_realized(base_raw: dict, st_delta: Money, lt_delta: Money) -> dict:
    out = copy.deepcopy(base_raw)
    st = Decimal(str(get_path(out, "income.investment.short_term_gains", 0) or 0))
    lt = Decimal(str(get_path(out, "income.investment.long_term_gains", 0) or 0))
    set_path(out, "income.investment.short_term_gains",
             str(st + st_delta.amount))
    set_path(out, "income.investment.long_term_gains",
             str(lt + lt_delta.amount))
    return out


def _run(raw: dict, data: ResolvedData, build: BuildInput) -> TaxResult:
    return pipeline.run(build(raw), data, compute_marginals=False)


def benefit_of(base_raw: dict, data: ResolvedData, build: BuildInput,
               st_delta: Money, lt_delta: Money,
               baseline: TaxResult | None = None) -> Money:
    if baseline is None:
        baseline = _run(base_raw, data, build)
    after = _run(with_realized(base_raw, st_delta, lt_delta), data, build)
    return (baseline.total_tax_all_jurisdictions
            - after.total_tax_all_jurisdictions)


@dataclass(frozen=True)
class MarginalRates:
    short_term: Decimal   # combined marginal rate on the next $1,000 of ST gain
    long_term: Decimal


def marginal_gain_rates(base_raw: dict, data: ResolvedData,
                        build: BuildInput,
                        baseline: TaxResult | None = None) -> MarginalRates:
    """Computed numerically, like all marginal rates (spec §9.10)."""
    if baseline is None:
        baseline = _run(base_raw, data, build)
    step = Money(1000)
    st = _run(with_realized(base_raw, step, ZERO), data, build)
    lt = _run(with_realized(base_raw, ZERO, step), data, build)
    return MarginalRates(
        short_term=(st.total_tax_all_jurisdictions
                    - baseline.total_tax_all_jurisdictions).ratio(step)
        .quantize(Decimal("0.0001")),
        long_term=(lt.total_tax_all_jurisdictions
                   - baseline.total_tax_all_jurisdictions).ratio(step)
        .quantize(Decimal("0.0001")),
    )


@dataclass(frozen=True)
class Candidate:
    lot: Lot
    character: str            # short | long
    unrealized: Money         # negative
    tax_benefit: Money        # from the full pipeline rerun
    wash: washsale.WashSaleRisk
    excluded_reason: str = ""


def scan(lots: list[Lot], base_raw: dict, data: ResolvedData,
         build: BuildInput, *, as_of: date,
         min_benefit: Money = ZERO) -> tuple[list[Candidate], list[Candidate]]:
    """Returns (candidates sorted by benefit desc, excluded-with-reason)."""
    baseline = _run(base_raw, data, build)
    candidates: list[Candidate] = []
    excluded: list[Candidate] = []
    for lot in lots:
        if lot.unrealized >= ZERO:
            continue
        wash_risk = washsale.check(lot, lots, as_of)
        if lot.is_ira:
            excluded.append(Candidate(
                lot=lot, character=lot.character(as_of),
                unrealized=lot.unrealized, tax_benefit=ZERO, wash=wash_risk,
                excluded_reason="IRA lot — a loss there has no tax value"))
            continue
        character = lot.character(as_of)
        loss = lot.unrealized  # negative
        st_delta = loss if character == "short" else ZERO
        lt_delta = loss if character == "long" else ZERO
        benefit = benefit_of(base_raw, data, build, st_delta, lt_delta,
                             baseline=baseline)
        if benefit < min_benefit:
            continue
        candidates.append(Candidate(
            lot=lot, character=character, unrealized=loss,
            tax_benefit=benefit, wash=wash_risk))
    candidates.sort(key=lambda c: c.tax_benefit.cents, reverse=True)
    return candidates, excluded


@dataclass(frozen=True)
class NettingWalk:
    st_realized: Money        # deltas realized by the simulated sale
    lt_realized: Money
    ordinary_offset: Money    # loss applied against ordinary income (<= 0)
    carryforward_st: Money
    carryforward_lt: Money


@dataclass(frozen=True)
class Simulation:
    lots_sold: tuple[Lot, ...]
    before: TaxResult
    after: TaxResult
    netting: NettingWalk
    basis_reduction: Money        # deferred cost driver
    future_rate: Decimal
    future_tax_cost: Money
    npv_benefit: Money
    discount_rate: Decimal
    horizon_years: int
    wash_risks: tuple[washsale.WashSaleRisk, ...]

    @property
    def tax_saved_now(self) -> Money:
        return (self.before.total_tax_all_jurisdictions
                - self.after.total_tax_all_jurisdictions)


def simulate(lot_ids: list[str], lots: list[Lot], base_raw: dict,
             data: ResolvedData, build: BuildInput, *, as_of: date,
             future_rate: Decimal | None = None,
             discount_rate: Decimal = Decimal("0.05"),
             horizon_years: int = 10) -> Simulation:
    by_id = {lot.lot_id: lot for lot in lots}
    missing = [i for i in lot_ids if i not in by_id]
    if missing:
        raise UsageError(f"unknown lot id(s): {', '.join(missing)}",
                         hint="see `ouch harvest scan` for lot ids")
    sold = [by_id[i] for i in lot_ids]
    ira = [lot for lot in sold if lot.is_ira]
    if ira:
        raise UsageError(
            f"lot(s) in IRA accounts cannot be harvested: "
            f"{', '.join(l.lot_id for l in ira)}",
            hint="a loss inside an IRA has no tax value")

    st_delta = sum((lot.unrealized for lot in sold
                    if not lot.is_long_term(as_of)), ZERO)
    lt_delta = sum((lot.unrealized for lot in sold
                    if lot.is_long_term(as_of)), ZERO)

    before = _run(base_raw, data, build)
    after_raw = with_realized(base_raw, st_delta, lt_delta)
    after = _run(after_raw, data, build)

    # Netting walk on the post-sale totals, for display (IRC §1211 ordering).
    inv_path = "income.investment."
    status = build(base_raw).taxpayer.filing_status
    offset_limit = Money(
        data.federal.capital_loss.mfs_offset
        if status == FilingStatus.MARRIED_FILING_SEPARATELY
        else data.federal.capital_loss.annual_ordinary_offset)
    st_total = Money(str(get_path(after_raw, inv_path + "short_term_gains", 0) or 0))
    lt_total = Money(str(get_path(after_raw, inv_path + "long_term_gains", 0) or 0))
    carry_in = Money(str(get_path(after_raw, inv_path + "capital_loss_carryforward", 0) or 0))
    netting = net_capital(st_total, lt_total, carry_in, ZERO, ZERO, offset_limit)

    if future_rate is None:
        # Default assumed future rate = current marginal LTCG rate (§13.4)
        future_rate = marginal_gain_rates(base_raw, data, build,
                                          baseline=before).long_term

    basis_reduction = -(st_delta + lt_delta)  # positive: future gains grow
    future_tax_cost = basis_reduction * future_rate
    # NPV: tax saved now minus the discounted future cost.
    discount_factor = (Decimal(1) + discount_rate) ** horizon_years
    tax_saved = (before.total_tax_all_jurisdictions
                 - after.total_tax_all_jurisdictions)
    npv = tax_saved - future_tax_cost / discount_factor

    return Simulation(
        lots_sold=tuple(sold), before=before, after=after,
        netting=NettingWalk(
            st_realized=st_delta, lt_realized=lt_delta,
            ordinary_offset=minm(netting.ordinary_component, ZERO),
            carryforward_st=netting.carryforward_st,
            carryforward_lt=netting.carryforward_lt),
        basis_reduction=basis_reduction, future_rate=future_rate,
        future_tax_cost=future_tax_cost.round_cent(),
        npv_benefit=npv.round_cent(), discount_rate=discount_rate,
        horizon_years=horizon_years,
        wash_risks=tuple(washsale.check(lot, lots, as_of) for lot in sold))


def zero_band_room(result: TaxResult, data: ResolvedData,
                   status: FilingStatus) -> Money:
    """Gain harvesting (spec §13.6): room remaining in the 0% preferential
    band — LTCG realizable at a 0% federal rate."""
    first = data.federal.preferential_brackets[status][0]
    if first.rate != 0 or first.up_to is None:
        return ZERO
    return maxm(ZERO, Money(first.up_to) - result.taxable_income)


def holding_period_alerts(lots: list[Lot], as_of: date,
                          within_days: int = 60) -> list[tuple[Lot, int]]:
    """Lots with unrealized gains approaching the one-year long-term
    boundary, where waiting materially changes the rate (spec §13.6)."""
    alerts = []
    for lot in lots:
        if lot.is_ira or lot.unrealized <= ZERO:
            continue
        days = lot.days_to_long_term(as_of)
        if 0 < days <= within_days:
            alerts.append((lot, days))
    alerts.sort(key=lambda pair: pair[1])
    return alerts
