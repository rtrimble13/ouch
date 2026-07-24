"""Bracket application. Pure; operates on Money with Decimal rates."""

from __future__ import annotations

from ouch.model.money import Money, ZERO, minm
from ouch.taxdata.schema import Bracket


def apply_brackets(amount: Money, brackets: list[Bracket]) -> Money:
    """Progressive tax on `amount` through ascending brackets.

    Bracket computations use unrounded inputs (spec §7.1).
    """
    if amount <= ZERO:
        return ZERO
    tax = ZERO
    lower = ZERO
    for b in brackets:
        top = None if b.up_to is None else Money(b.up_to)
        ceiling = amount if top is None else minm(amount, top)
        span = ceiling - lower
        if span > ZERO:
            tax += span * b.rate
        if top is None or amount <= top:
            break
        lower = top
    return tax
