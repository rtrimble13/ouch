"""The preferential rate stacking test matrix (spec §9.4) — every expected
value below is hand-computed from the fabricated brackets, never derived from
the code under test.

Fabricated brackets:
  ordinary:      10% to 10,000 · 20% to 50,000 · 30% above
  preferential:   0% to 20,000 · 15% to 100,000 · 20% above
  special:       §1250 25% · collectibles 28%
"""

from decimal import Decimal

from ouch.engine.federal import federal_income_tax
from ouch.engine.income import net_capital
from ouch.model.money import Money, ZERO
from ouch.taxdata.schema import Bracket, SpecialRateGroups

ORDINARY = [Bracket(up_to=Decimal(10_000), rate=Decimal("0.10")),
            Bracket(up_to=Decimal(50_000), rate=Decimal("0.20")),
            Bracket(up_to=None, rate=Decimal("0.30"))]
PREF = [Bracket(up_to=Decimal(20_000), rate=Decimal("0.00")),
        Bracket(up_to=Decimal(100_000), rate=Decimal("0.15")),
        Bracket(up_to=None, rate=Decimal("0.20"))]
SPECIAL = SpecialRateGroups(unrecaptured_1250=Decimal("0.25"),
                            collectibles=Decimal("0.28"))


def tax(taxable, pref, **kw):
    return federal_income_tax(Money(taxable), Money(pref), ORDINARY, PREF, **kw)


def test_1_all_ordinary_no_preferential():
    # 10%×10,000 + 20%×40,000 + 30%×10,000 = 1,000 + 8,000 + 3,000
    t = tax(60_000, 0)
    assert t.ordinary == Money(12_000)
    assert t.preferential == ZERO


def test_2_all_preferential_zero_ordinary():
    # 0% band fully used: 20,000@0% + 10,000@15% = 1,500
    t = tax(30_000, 30_000)
    assert t.ordinary == ZERO
    assert t.preferential == Money(1_500)


def test_3_preferential_straddles_0_15_boundary():
    # ordinary 15,000 → 1,000 + 20%×5,000 = 2,000
    # pref 10,000 stacks from 15,000: 5,000@0% + 5,000@15% = 750
    t = tax(25_000, 10_000)
    assert t.ordinary == Money(2_000)
    assert t.preferential == Money(750)


def test_4_preferential_straddles_15_20_boundary():
    # ordinary 60,000 → 12,000; pref 50,000 from 60,000:
    # 40,000@15% + 10,000@20% = 8,000
    t = tax(110_000, 50_000)
    assert t.ordinary == Money(12_000)
    assert t.preferential == Money(8_000)


def test_5_ordinary_alone_exceeds_top_pref_threshold():
    # ordinary 120,000 → 1,000 + 8,000 + 30%×70,000 = 30,000
    # pref 10,000 entirely above 100,000 → all @20% = 2,000
    t = tax(130_000, 10_000)
    assert t.ordinary == Money(30_000)
    assert t.preferential == Money(2_000)


def test_7_capital_loss_reduces_pref_to_zero_with_ordinary_offset():
    n = net_capital(Money(-4_000), Money(2_000), ZERO, ZERO, ZERO,
                    offset_limit=Money(3_000))
    assert n.preferential_gain == ZERO
    assert n.ordinary_component == Money(-2_000)
    assert n.carryforward_st == ZERO and n.carryforward_lt == ZERO


def test_8_1250_and_collectibles_groups_simultaneously():
    # ordinary 60,000 → 12,000.
    # §1250 10,000: min(25%×10,000=2,500, as-ordinary 30%×10,000=3,000) = 2,500
    # collectibles 10,000: min(28%×10,000=2,800, 3,000) = 2,800
    t = tax(80_000, 0, unrecap_1250=Money(10_000),
            collectibles=Money(10_000), special_rates=SPECIAL)
    assert t.ordinary == Money(12_000)
    assert t.special == Money(5_300)


def test_special_group_capped_at_ordinary_rate():
    # ordinary 5,000 → 500. §1250 3,000 as-ordinary: 10%×3,000 = 300 < 25%×3,000
    t = tax(8_000, 0, unrecap_1250=Money(3_000), special_rates=SPECIAL)
    assert t.special == Money(300)


def test_ordinary_taxed_as_if_pref_absent():
    # Regression guard for the classic amateur error: with pref present,
    # ordinary tax must equal the ordinary-only computation.
    with_pref = tax(80_000, 20_000)
    alone = tax(60_000, 0)
    assert with_pref.ordinary == alone.ordinary
