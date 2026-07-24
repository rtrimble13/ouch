"""§1091 wash-sale window analysis (spec §13.3).

For a candidate sale of security S on date D, purchases of S in ANY account
inside [D−30, D+30] disallow the loss pro-rata by shares repurchased.
Purchases in an IRA disallow it PERMANENTLY — the basis adjustment has
nowhere to go.

"Substantially identical" is a legal judgment the tool will not make
definitively: exact-symbol matches are flagged as certain; cross-issuer
same-index equivalence is not assessed (fidelity: approximate, and the
output says so).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

from ouch.model.money import Money, ZERO
from ouch.model.portfolio import Lot

WINDOW_DAYS = 30


@dataclass(frozen=True)
class Conflict:
    lot: Lot
    shares: Decimal          # shares purchased inside the window
    permanent: bool          # purchase in an IRA — loss permanently disallowed


@dataclass(frozen=True)
class WashSaleRisk:
    sale_lot: Lot
    sale_date: date
    conflicts: tuple[Conflict, ...] = ()
    disallowed_shares: Decimal = Decimal(0)
    disallowed_loss: Money = ZERO
    permanent: bool = False

    @property
    def clear(self) -> bool:
        return not self.conflicts

    @property
    def allowed_loss(self) -> Money:
        loss = self.sale_lot.unrealized
        if loss >= ZERO:
            return ZERO
        return -(loss) - self.disallowed_loss  # positive magnitudes


def check(sale_lot: Lot, all_lots: list[Lot], sale_date: date) -> WashSaleRisk:
    """Wash-sale exposure for selling `sale_lot` (entirely) on `sale_date`.

    Replacement purchases are inferred from lots of the same symbol acquired
    inside the 61-day window — this catches DRIP and recurring buys that
    appear as recent lots. Purchases after `sale_date` that are not yet lots
    obviously cannot be seen; the output warns about the forward window.
    """
    if sale_lot.unrealized >= ZERO:
        return WashSaleRisk(sale_lot=sale_lot, sale_date=sale_date)

    lo = sale_date - timedelta(days=WINDOW_DAYS)
    hi = sale_date + timedelta(days=WINDOW_DAYS)
    conflicts: list[Conflict] = []
    for other in all_lots:
        if other.lot_id == sale_lot.lot_id:
            continue
        if other.symbol != sale_lot.symbol:
            continue  # cross-issuer equivalence not assessed (approximate)
        if lo <= other.acquired_date <= hi:
            conflicts.append(Conflict(lot=other, shares=other.quantity,
                                      permanent=other.is_ira))

    if not conflicts:
        return WashSaleRisk(sale_lot=sale_lot, sale_date=sale_date)

    repurchased = sum((c.shares for c in conflicts), Decimal(0))
    disallowed_shares = min(repurchased, sale_lot.quantity)
    loss_magnitude = -sale_lot.unrealized  # positive
    disallowed_loss = loss_magnitude * (disallowed_shares / sale_lot.quantity)
    return WashSaleRisk(
        sale_lot=sale_lot, sale_date=sale_date, conflicts=tuple(conflicts),
        disallowed_shares=disallowed_shares,
        disallowed_loss=disallowed_loss.round_cent(),
        permanent=any(c.permanent for c in conflicts))
