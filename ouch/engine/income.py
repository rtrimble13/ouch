"""Income classification and capital gain netting (spec §9.2).

Capital gain netting follows the statutory order: net short-term against
short-term, long-term against long-term, then cross-net; apply the annual
ordinary-income offset limit; carry the remainder forward with character
preserved (ST/LT).
"""

from __future__ import annotations

from dataclasses import dataclass

from ouch.model.money import Money, ZERO, maxm, minm


@dataclass(frozen=True)
class CapitalNetting:
    st_net: Money              # after cross-netting (may be negative only when overall loss)
    lt_net: Money
    preferential_gain: Money   # net LT gain feeding the 0/15/20 stack (excl. special groups)
    unrecap_1250: Money        # 25% group (carved out of LT net gain)
    collectibles: Money        # 28% group
    ordinary_component: Money  # ST net gain (+) or the allowed loss offset (−)
    carryforward_st: Money     # losses carried to next year, character preserved
    carryforward_lt: Money


def net_capital(short_term: Money, long_term: Money, carryforward_loss: Money,
                unrecap_1250: Money, collectibles: Money,
                offset_limit: Money) -> CapitalNetting:
    """`carryforward_loss` is a positive number of loss carried in, treated as
    long-term character (the profile carries a single figure; approximate).
    `unrecap_1250` / `collectibles` are carve-outs within `long_term`.
    """
    st = short_term
    lt = long_term - carryforward_loss

    # Cross-net when signs oppose.
    if st < ZERO < lt:
        x = minm(-st, lt)
        st += x
        lt -= x
    elif lt < ZERO < st:
        x = minm(-lt, st)
        lt += x
        st -= x

    total = st + lt
    if total >= ZERO:
        lt_gain = maxm(lt, ZERO)
        # Special rate groups are carved out of the LT net gain, capped by it.
        g1250 = minm(unrecap_1250, lt_gain)
        g28 = minm(collectibles, lt_gain - g1250)
        return CapitalNetting(
            st_net=st, lt_net=lt,
            preferential_gain=lt_gain - g1250 - g28,
            unrecap_1250=g1250, collectibles=g28,
            ordinary_component=maxm(st, ZERO),
            carryforward_st=ZERO, carryforward_lt=ZERO,
        )

    # Overall loss: limited ordinary offset, remainder carried with character.
    allowed = minm(-total, offset_limit)
    st_loss = maxm(-st, ZERO)
    lt_loss = maxm(-lt, ZERO)
    st_used = minm(st_loss, allowed)     # ST losses absorb the offset first
    lt_used = allowed - st_used
    return CapitalNetting(
        st_net=st, lt_net=lt,
        preferential_gain=ZERO, unrecap_1250=ZERO, collectibles=ZERO,
        ordinary_component=-allowed,
        carryforward_st=st_loss - st_used,
        carryforward_lt=lt_loss - lt_used,
    )
