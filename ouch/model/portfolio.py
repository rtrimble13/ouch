"""Portfolio models: Lot and holding-period logic (spec §7 layout, §13)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from ouch.model.money import Money, ZERO

LONG_TERM_DAYS = 365  # long-term when held MORE than one year (approximate:
                      # counted in days; the statutory more-than-one-year test
                      # differs by at most a day around leap years)


@dataclass(frozen=True)
class Lot:
    account: str
    symbol: str
    lot_id: str
    quantity: Decimal
    acquired_date: date
    cost_basis: Money        # total for the lot
    current_price: Money     # per share
    as_of: date
    asset_class: str = ""
    is_ira: bool = False

    @property
    def market_value(self) -> Money:
        return self.current_price * self.quantity

    @property
    def unrealized(self) -> Money:
        return self.market_value - self.cost_basis

    def is_long_term(self, sale_date: date) -> bool:
        return (sale_date - self.acquired_date).days > LONG_TERM_DAYS

    def character(self, sale_date: date) -> str:
        return "long" if self.is_long_term(sale_date) else "short"

    def days_to_long_term(self, on: date) -> int:
        """Days until the lot crosses the one-year boundary (<= 0 if past)."""
        boundary = self.acquired_date + timedelta(days=LONG_TERM_DAYS + 1)
        return (boundary - on).days
