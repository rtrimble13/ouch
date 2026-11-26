"""Tax-loss harvesting: lots, wash sales, pipeline-true benefits (spec §13)."""

from __future__ import annotations

import datetime as _dt
from decimal import Decimal
from pathlib import Path

import pytest

from ouch.config.profile import build_tax_input
from ouch.errors import UsageError, ValidationInputError
from ouch.harvest import lots as lots_mod
from ouch.harvest import ranker, washsale
from ouch.model.enums import FilingStatus
from ouch.model.money import Money, ZERO
from ouch.model.portfolio import Lot

AS_OF = _dt.date(2025, 12, 12)


def make_lot(lot_id="L-1", symbol="VTI", quantity="10", acquired="2025-02-01",
             cost="2000", price="150", is_ira=False, account="Brokerage"):
    return Lot(account=account, symbol=symbol, lot_id=lot_id,
               quantity=Decimal(quantity),
               acquired_date=_dt.date.fromisoformat(acquired),
               cost_basis=Money(cost), current_price=Money(price),
               as_of=AS_OF, is_ira=is_ira)


def _build(raw):
    return build_tax_input(raw, 2025)


BASE = {
    "tax_year": 2025,
    "taxpayer": {"filing_status": "single", "state": ""},
    "income": {"wages": {"taxpayer_w2": 100_000},
               "investment": {"short_term_gains": 10_000,
                              "long_term_gains": 5_000}},
}


# ----- lot model ------------------------------------------------------------


def test_lot_unrealized_and_character():
    lot = make_lot(quantity="10", cost="2000", price="150")  # value 1500
    assert lot.unrealized == Money(-500)
    assert lot.character(AS_OF) == "short"
    old = make_lot(acquired="2024-06-01")
    assert old.character(AS_OF) == "long"


def test_days_to_long_term():
    lot = make_lot(acquired="2025-01-20")
    # boundary = 2025-01-20 + 366 days = 2026-01-21 → 40 days from 2025-12-12
    assert lot.days_to_long_term(AS_OF) == 40


# ----- CSV ingestion --------------------------------------------------------


CSV_HEADER = ("account,symbol,lot_id,quantity,acquired_date,cost_basis,"
              "current_price,as_of,asset_class,is_ira\n")


def test_parse_valid_csv(tmp_path: Path):
    f = tmp_path / "lots.csv"
    f.write_text(CSV_HEADER
                 + "Brokerage,VTI,L-1,10,2025-02-01,2000,150,2025-12-12,eq,false\n"
                 + "IRA,VTI,L-2,5,2025-03-01,1000,150,2025-12-12,eq,true\n")
    lots = lots_mod.parse_lots_csv(f)
    assert len(lots) == 2
    assert lots[1].is_ira is True


def test_parse_errors_collected_together(tmp_path: Path):
    f = tmp_path / "bad.csv"
    f.write_text(CSV_HEADER
                 + "Brokerage,VTI,L-1,-3,2025-02-01,2000,150,2025-12-12,eq,false\n"
                 + "Brokerage,VTI,L-2,5,not-a-date,1000,150,2025-12-12,eq,false\n"
                 + "Brokerage,VTI,L-3,5,2025-02-01,1000,150,2025-12-12,eq,maybe\n")
    with pytest.raises(ValidationInputError) as e:
        lots_mod.parse_lots_csv(f)
    msg = str(e.value)
    assert "3 errors" in msg
    assert "quantity must be positive" in msg
    assert "bad date" in msg
    assert "is_ira" in msg


def test_duplicate_lot_id_rejected(tmp_path: Path):
    f = tmp_path / "dup.csv"
    f.write_text(CSV_HEADER
                 + "B,VTI,L-1,10,2025-02-01,2000,150,2025-12-12,eq,false\n"
                 + "B,VTI,L-1,10,2025-03-01,2000,150,2025-12-12,eq,false\n")
    with pytest.raises(ValidationInputError) as e:
        lots_mod.parse_lots_csv(f)
    assert "duplicate lot_id" in str(e.value)


def test_missing_column_rejected(tmp_path: Path):
    f = tmp_path / "cols.csv"
    f.write_text("account,symbol\nB,VTI\n")
    with pytest.raises(ValidationInputError) as e:
        lots_mod.parse_lots_csv(f)
    assert "missing columns" in str(e.value)


def test_save_load_roundtrip(tmp_path: Path):
    lots = [make_lot(lot_id="L-1"), make_lot(lot_id="L-2", is_ira=True)]
    target = tmp_path / "portfolio.csv"
    lots_mod.save_portfolio(lots, target)
    loaded = lots_mod.parse_lots_csv(target)
    assert [l.lot_id for l in loaded] == ["L-1", "L-2"]
    assert loaded[0].unrealized == lots[0].unrealized


# ----- wash sales -----------------------------------------------------------


def test_washsale_clear():
    loss = make_lot(lot_id="L-1", acquired="2025-05-01")
    other_symbol = make_lot(lot_id="L-2", symbol="BND", acquired="2025-12-01")
    old_purchase = make_lot(lot_id="L-3", acquired="2025-09-01")  # outside window
    risk = washsale.check(loss, [loss, other_symbol, old_purchase], AS_OF)
    assert risk.clear


def test_washsale_drip_pro_rata():
    """41 shares sold at an $8,240 loss; a 3.114-share DRIP inside the
    window disallows 3.114/41 of the loss ≈ $625.72."""
    loss = Lot(account="B", symbol="VXUS", lot_id="L-431",
               quantity=Decimal(41), acquired_date=_dt.date(2025, 8, 1),
               cost_basis=Money("10300"), current_price=Money("50.2439"),
               as_of=AS_OF)
    drip = Lot(account="B", symbol="VXUS", lot_id="L-900",
               quantity=Decimal("3.114"), acquired_date=_dt.date(2025, 11, 28),
               cost_basis=Money("156"), current_price=Money("50.2439"),
               as_of=AS_OF)
    risk = washsale.check(loss, [loss, drip], AS_OF)
    assert not risk.clear
    assert risk.disallowed_shares == Decimal("3.114")
    loss_total = -loss.unrealized
    expected = (loss_total * (Decimal("3.114") / 41)).round_cent()
    assert risk.disallowed_loss == expected
    assert not risk.permanent


def test_washsale_ira_permanent():
    loss = make_lot(lot_id="L-1", symbol="IEFA", acquired="2024-01-01")
    ira_buy = make_lot(lot_id="L-2", symbol="IEFA", acquired="2025-11-20",
                       is_ira=True, account="IRA")
    risk = washsale.check(loss, [loss, ira_buy], AS_OF)
    assert risk.permanent


def test_washsale_gain_lot_no_risk():
    gain = make_lot(cost="1000", price="150")  # value 1500 > basis
    rebuy = make_lot(lot_id="L-2", acquired="2025-12-01")
    risk = washsale.check(gain, [gain, rebuy], AS_OF)
    assert risk.clear


def test_washsale_disallowed_capped_at_sold_shares():
    loss = make_lot(lot_id="L-1", quantity="5", cost="1000", price="100")
    big_rebuy = make_lot(lot_id="L-2", quantity="50", acquired="2025-12-01")
    risk = washsale.check(loss, [loss, big_rebuy], AS_OF)
    assert risk.disallowed_shares == Decimal(5)
    assert risk.disallowed_loss == -loss.unrealized  # fully disallowed


# ----- benefit quantification ----------------------------------------------


def test_benefit_equals_pipeline_delta(data_federal_only):
    """A $5,000 ST loss against $10,000 of realized ST gains sits entirely
    in the 22% bracket at this income → benefit = 5,000 × 22% = 1,100."""
    benefit = ranker.benefit_of(BASE, data_federal_only, _build,
                                Money(-5_000), ZERO)
    assert benefit == Money(1_100)


def test_benefit_respects_offset_limit(data_federal_only):
    """With gains exhausted, extra loss only offsets $3,000 of ordinary
    income this year — the benefit must NOT scale linearly."""
    small = ranker.benefit_of(BASE, data_federal_only, _build,
                              Money(-15_000), ZERO)
    huge = ranker.benefit_of(BASE, data_federal_only, _build,
                             Money(-100_000), ZERO)
    # 15k offsets 10k ST gains + 5k of LT gain; 100k adds only the 3k
    # ordinary offset beyond gains — nowhere near linear.
    assert huge < small * 3
    assert huge > small  # but still somewhat better


def test_st_loss_worth_more_than_lt_loss(data_federal_only):
    """ST losses offset ST gains (ordinary rates) first — worth more than
    the same LT loss when both gain kinds are realized (spec §13.4)."""
    st = ranker.benefit_of(BASE, data_federal_only, _build, Money(-4_000), ZERO)
    lt = ranker.benefit_of(BASE, data_federal_only, _build, ZERO, Money(-4_000))
    assert st > lt


def test_scan_excludes_ira_and_ranks(data_federal_only):
    lots = [
        make_lot(lot_id="BIG", quantity="100", cost="30000", price="150"),   # −15,000
        make_lot(lot_id="SMALL", quantity="10", cost="2000", price="150"),   # −500
        make_lot(lot_id="IRA-1", quantity="10", cost="5000", price="150",
                 is_ira=True, account="IRA"),                                # −3,500 IRA
        make_lot(lot_id="GAIN", quantity="10", cost="1000", price="150"),    # +500
    ]
    candidates, excluded = ranker.scan(lots, BASE, data_federal_only, _build,
                                       as_of=AS_OF)
    assert [c.lot.lot_id for c in candidates] == ["BIG", "SMALL"]
    assert candidates[0].tax_benefit > candidates[1].tax_benefit
    assert len(excluded) == 1 and excluded[0].lot.lot_id == "IRA-1"


def test_simulate_carryforward_and_deferred_cost(data_federal_only):
    lots = [make_lot(lot_id="BIG", quantity="100", cost="40000",
                     price="150")]  # −25,000 ST loss
    sim = ranker.simulate(["BIG"], lots, BASE, data_federal_only, _build,
                          as_of=AS_OF, future_rate=Decimal("0.15"))
    # 25k loss vs 10k ST + 5k LT gains → 10k excess → 3k ordinary offset,
    # 7k carryforward (ST character preserved)
    assert sim.netting.ordinary_offset == Money(-3_000)
    assert sim.netting.carryforward_st == Money(7_000)
    assert sim.netting.carryforward_lt == ZERO
    assert sim.basis_reduction == Money(25_000)
    assert sim.future_tax_cost == Money(25_000) * Decimal("0.15")
    assert sim.tax_saved_now > ZERO
    # NPV = saved − future/(1.05^10)
    expected_npv = (sim.tax_saved_now
                    - sim.future_tax_cost / (Decimal("1.05") ** 10))
    assert abs(sim.npv_benefit - expected_npv) <= Money("0.01")


def test_simulate_refuses_ira_and_unknown(data_federal_only):
    lots = [make_lot(lot_id="IRA-1", is_ira=True)]
    with pytest.raises(UsageError):
        ranker.simulate(["IRA-1"], lots, BASE, data_federal_only, _build,
                        as_of=AS_OF)
    with pytest.raises(UsageError):
        ranker.simulate(["NOPE"], lots, BASE, data_federal_only, _build,
                        as_of=AS_OF)


def test_zero_band_room(data_federal_only):
    """Single, 40k wages → taxable 40,000 − 15,750 = 24,250; 0% band tops at
    48,350 → 24,100 of gain-harvesting room."""
    low = {"tax_year": 2025,
           "taxpayer": {"filing_status": "single", "state": ""},
           "income": {"wages": {"taxpayer_w2": 40_000}}}
    result = ranker._run(low, data_federal_only, _build)
    room = ranker.zero_band_room(result, data_federal_only,
                                 FilingStatus.SINGLE)
    assert room == Money(24_100)


def test_holding_period_alerts():
    near = make_lot(lot_id="NEAR", cost="1000", price="150",
                    acquired="2025-01-20")     # gain, 40 days to boundary
    far = make_lot(lot_id="FAR", cost="1000", price="150",
                   acquired="2025-10-01")      # gain, far from boundary
    loss = make_lot(lot_id="LOSS", cost="3000", price="150",
                    acquired="2025-01-20")     # loss — no alert
    alerts = ranker.holding_period_alerts([near, far, loss], AS_OF)
    assert [(l.lot_id, d) for l, d in alerts] == [("NEAR", 40)]
