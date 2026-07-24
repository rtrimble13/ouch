from decimal import Decimal

import pytest

from ouch.model.money import Money, ZERO, maxm, minm


def test_construction_from_str_int_decimal():
    assert Money("12.34").amount == Decimal("12.34")
    assert Money(12).amount == Decimal(12)
    assert Money(Decimal("0.5")).amount == Decimal("0.5")


def test_float_construction_raises():
    with pytest.raises(TypeError):
        Money(1.5)  # type: ignore[arg-type]


def test_float_arithmetic_raises():
    with pytest.raises(TypeError):
        Money("1") * 0.5  # type: ignore[operator]
    with pytest.raises(TypeError):
        Money("1") / 0.5  # type: ignore[operator]


def test_arithmetic():
    assert (Money("10") + Money("2.50")).amount == Decimal("12.50")
    assert (Money("10") - Money("2.50")).amount == Decimal("7.50")
    assert (Money("10") * Decimal("0.22")).amount == Decimal("2.20")
    assert (-Money("3")).amount == Decimal("-3")
    assert abs(Money("-3")) == Money("3")


def test_round_dollar_half_up():
    assert Money("2.50").round_dollar() == Money("3")
    assert Money("2.49").round_dollar() == Money("2")
    assert Money("-2.50").round_dollar() == Money("-3")  # HALF_UP on magnitude


def test_round_cent_half_even():
    assert Money("0.005").round_cent().amount == Decimal("0.00")
    assert Money("0.015").round_cent().amount == Decimal("0.02")


def test_intermediate_precision_retained():
    # Division keeps sub-cent precision until an explicit rounding call;
    # 28 significant digits of Decimal context, so the round-trip error is
    # far below a cent and vanishes under explicit rounding.
    third = Money("1") / 3
    assert third.amount != Decimal("0.33")  # not silently rounded
    assert (third * 3).round_cent() == Money("1")


def test_comparisons_and_helpers():
    assert Money("5") > Money("4")
    assert maxm(Money("1"), Money("2")) == Money("2")
    assert minm(Money("1"), Money("2")) == Money("1")
    assert bool(ZERO) is False


def test_sum_with_zero_start():
    assert sum([Money("1"), Money("2")], ZERO) == Money("3")
