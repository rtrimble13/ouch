"""Capital netting: statutory order, character preservation (spec §9.2)."""

from ouch.engine.income import net_capital
from ouch.model.money import Money, ZERO

LIMIT = Money(3_000)


def n(st, lt, cf=0, g1250=0, g28=0, limit=LIMIT):
    return net_capital(Money(st), Money(lt), Money(cf), Money(g1250),
                       Money(g28), limit)


def test_both_gains():
    r = n(5_000, 10_000)
    assert r.ordinary_component == Money(5_000)
    assert r.preferential_gain == Money(10_000)


def test_st_loss_offsets_lt_gain():
    r = n(-6_000, 10_000)
    assert r.preferential_gain == Money(4_000)
    assert r.ordinary_component == ZERO


def test_lt_loss_offsets_st_gain():
    r = n(8_000, -5_000)
    assert r.ordinary_component == Money(3_000)
    assert r.preferential_gain == ZERO


def test_overall_loss_limited_to_offset():
    r = n(-10_000, 2_000)
    # cross-net → ST −8,000; offset limited to 3,000; carry 5,000 as ST
    assert r.ordinary_component == Money(-3_000)
    assert r.carryforward_st == Money(5_000)
    assert r.carryforward_lt == ZERO


def test_character_preserved_in_carryforward():
    r = n(-4_000, -2_000)
    # ST absorbs the 3,000 offset first → carry ST 1,000, LT 2,000
    assert r.ordinary_component == Money(-3_000)
    assert r.carryforward_st == Money(1_000)
    assert r.carryforward_lt == Money(2_000)


def test_carryforward_in_reduces_lt():
    r = n(0, 10_000, cf=4_000)
    assert r.preferential_gain == Money(6_000)


def test_mfs_offset_limit():
    r = n(-5_000, 0, limit=Money(1_500))
    assert r.ordinary_component == Money(-1_500)
    assert r.carryforward_st == Money(3_500)


def test_special_groups_carved_from_lt_gain():
    r = n(0, 10_000, g1250=3_000, g28=2_000)
    assert r.unrecap_1250 == Money(3_000)
    assert r.collectibles == Money(2_000)
    assert r.preferential_gain == Money(5_000)
