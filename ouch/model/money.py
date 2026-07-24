"""Decimal-backed Money type. No float arithmetic anywhere in ouch (spec §7.1).

Rounding policy: intermediate values retain (fractional) cents. Only values
that would appear on a return line are rounded to whole dollars, ROUND_HALF_UP,
at the point the line is emitted. Bracket computations use unrounded inputs.
"""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_EVEN, ROUND_HALF_UP
from typing import Union

_Scalar = Union[int, Decimal, str]


class Money:
    """Immutable money value backed by a Decimal count of cents."""

    __slots__ = ("_cents",)

    def __init__(self, value: "Money | str | int | Decimal" = 0):
        if isinstance(value, Money):
            object.__setattr__(self, "_cents", value._cents)
            return
        if isinstance(value, float):
            raise TypeError(
                "Money cannot be constructed from float; pass str, int, or Decimal"
            )
        if not isinstance(value, (str, int, Decimal)):
            raise TypeError(f"cannot construct Money from {type(value).__name__}")
        object.__setattr__(self, "_cents", Decimal(value) * 100)

    @classmethod
    def from_cents(cls, cents: Decimal | int) -> "Money":
        m = cls.__new__(cls)
        object.__setattr__(m, "_cents", Decimal(cents))
        return m

    # ----- accessors -----

    @property
    def amount(self) -> Decimal:
        """Value in dollars as an exact Decimal."""
        return self._cents / 100

    @property
    def cents(self) -> Decimal:
        return self._cents

    # ----- rounding (always explicit, never implicit) -----

    def round_dollar(self) -> "Money":
        """IRS convention for return lines: whole dollars, ROUND_HALF_UP."""
        return Money(self.amount.quantize(Decimal("1"), rounding=ROUND_HALF_UP))

    def round_cent(self) -> "Money":
        """Intermediate accumulation: cents, ROUND_HALF_EVEN."""
        return Money.from_cents(self._cents.quantize(Decimal("1"), rounding=ROUND_HALF_EVEN))

    # ----- arithmetic -----

    def _coerce(self, other) -> "Money":
        if isinstance(other, Money):
            return other
        if isinstance(other, int) and other == 0:
            return ZERO
        raise TypeError(f"cannot combine Money with {type(other).__name__}")

    def __add__(self, other) -> "Money":
        return Money.from_cents(self._cents + self._coerce(other)._cents)

    __radd__ = __add__

    def __sub__(self, other) -> "Money":
        return Money.from_cents(self._cents - self._coerce(other)._cents)

    def __rsub__(self, other) -> "Money":
        return Money.from_cents(self._coerce(other)._cents - self._cents)

    def __mul__(self, scalar) -> "Money":
        if isinstance(scalar, float):
            raise TypeError("Money cannot be multiplied by float; use Decimal")
        if not isinstance(scalar, (int, Decimal)):
            raise TypeError(f"cannot multiply Money by {type(scalar).__name__}")
        return Money.from_cents(self._cents * Decimal(scalar))

    __rmul__ = __mul__

    def __truediv__(self, scalar) -> "Money":
        if isinstance(scalar, float):
            raise TypeError("Money cannot be divided by float; use Decimal")
        if not isinstance(scalar, (int, Decimal)):
            raise TypeError(f"cannot divide Money by {type(scalar).__name__}")
        return Money.from_cents(self._cents / Decimal(scalar))

    def ratio(self, other: "Money") -> Decimal:
        """self ÷ other as a pure Decimal ratio (e.g., for effective rates)."""
        if other._cents == 0:
            return Decimal(0)
        return self._cents / other._cents

    def __neg__(self) -> "Money":
        return Money.from_cents(-self._cents)

    def __abs__(self) -> "Money":
        return Money.from_cents(abs(self._cents))

    # ----- comparison -----

    def __eq__(self, other) -> bool:
        if isinstance(other, int) and other == 0:
            return self._cents == 0
        if not isinstance(other, Money):
            return NotImplemented
        return self._cents == other._cents

    def __lt__(self, other) -> bool:
        return self._cents < self._coerce(other)._cents

    def __le__(self, other) -> bool:
        return self._cents <= self._coerce(other)._cents

    def __gt__(self, other) -> bool:
        return self._cents > self._coerce(other)._cents

    def __ge__(self, other) -> bool:
        return self._cents >= self._coerce(other)._cents

    def __hash__(self) -> int:
        return hash(("Money", self._cents))

    def __bool__(self) -> bool:
        return self._cents != 0

    # ----- rendering -----

    def __str__(self) -> str:
        return f"{self.amount:,.2f}"

    def __repr__(self) -> str:
        return f"Money('{self.amount}')"

    def fmt(self, *, dollars: bool = True) -> str:
        """Display formatting; parenthesize negatives, e.g. `$ (4,180)`."""
        v = self.round_dollar().amount if dollars else self.amount
        pattern = "{:,.0f}" if dollars else "{:,.2f}"
        if v < 0:
            return "$ (" + pattern.format(-v) + ")"
        return "$ " + pattern.format(v)


ZERO = Money(0)


def maxm(*values: Money) -> Money:
    return max(values, key=lambda m: m.cents)


def minm(*values: Money) -> Money:
    return min(values, key=lambda m: m.cents)
