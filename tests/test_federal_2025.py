"""The 2025 federal data file against its primary sources (rtrimble13/ouch#27).

Identities inside Rev. Proc. 2024-40, which OBBBA left in force except for
the standard deduction (Rev. Proc. 2025-32 §3): its rate tables print the
tax at each bracket floor, its EITC table the completed phase-out amounts,
and its AMT table the complete phase-out of the exemption. Recomputing them
from the file's brackets and rates catches a mistyped number.
"""

from decimal import ROUND_HALF_UP, Decimal

import pytest

from ouch.engine.brackets import apply_brackets
from ouch.engine.federal import amt_additional
from ouch.model.enums import FilingStatus as F
from ouch.model.money import Money, ZERO

# §2.01 Tables 1–4: "If taxable income is over $X … the tax is $Y plus …"
RATE_TABLE_FLOORS = {
    F.MARRIED_FILING_JOINTLY: [(23_850, "2385"), (96_950, "11157"), (206_700, "35302"),
                               (394_600, "80398"), (501_050, "114462"),
                               (751_600, "202154.50")],
    F.HEAD_OF_HOUSEHOLD: [(17_000, "1700"), (64_850, "7442"), (103_350, "15912"),
                          (197_300, "38460"), (250_500, "55484"), (626_350, "187031.50")],
    F.SINGLE: [(11_925, "1192.50"), (48_475, "5578.50"), (103_350, "17651"),
               (197_300, "40199"), (250_525, "57231"), (626_350, "188769.75")],
    F.MARRIED_FILING_SEPARATELY: [(11_925, "1192.50"), (48_475, "5578.50"),
                                  (103_350, "17651"), (197_300, "40199"),
                                  (250_525, "57231"), (375_800, "101077.25")],
}
RATE_TABLE_FLOORS[F.QUALIFYING_SURVIVING_SPOUSE] = RATE_TABLE_FLOORS[F.MARRIED_FILING_JOINTLY]


@pytest.mark.parametrize("status", list(RATE_TABLE_FLOORS))
def test_brackets_reproduce_the_rate_tables(federal_2025, status):
    for taxable, tax in RATE_TABLE_FLOORS[status]:
        got = apply_brackets(Money(taxable), federal_2025.ordinary_brackets[status]).round_cent()
        assert got == Money(tax), (status, taxable)


# §2.06: completed phase-out amounts (MFJ, other), by number of children
EITC_COMPLETED = {0: (26_214, 19_104), 1: (57_554, 50_434),
                  2: (64_430, 57_310), 3: (68_675, 61_555)}


def test_eitc_table_is_internally_consistent(federal_2025):
    for tier in federal_2025.credits.eitc.by_children:
        max_credit = (tier.phase_in_rate * tier.earned_income_amount).quantize(
            Decimal(1), ROUND_HALF_UP)
        assert max_credit == tier.max_credit
        mfj, other = EITC_COMPLETED[tier.children]
        span = tier.max_credit / tier.phaseout_rate
        assert (tier.phaseout_start_mfj + span).quantize(Decimal(1)) == mfj
        assert (tier.phaseout_start_other + span).quantize(Decimal(1)) == other


@pytest.mark.parametrize("status, complete", [
    (F.MARRIED_FILING_JOINTLY, 1_800_700),
    (F.SINGLE, 978_750),
    (F.MARRIED_FILING_SEPARATELY, 900_350),
])
def test_amt_phaseout_rate_is_25_percent_in_2025(federal_2025, status, complete):
    """§2.11: the exemption is gone at threshold + 4 × exemption. OBBBA's
    50% rate starts in 2026."""
    amt = federal_2025.amt
    assert amt.phaseout_threshold[status] + amt.exemption[status] / amt.phaseout_rate == complete


def test_qbi_phase_in_ends(federal_2025):
    """§2.27 prints the end of the phase-in range; a qualifying surviving
    spouse is under "All Other Returns"."""
    q = federal_2025.qbi
    assert q.threshold[F.MARRIED_FILING_JOINTLY] + q.phase_in_range[F.MARRIED_FILING_JOINTLY] == 494_600
    for status in (F.SINGLE, F.MARRIED_FILING_SEPARATELY, F.HEAD_OF_HOUSEHOLD,
                   F.QUALIFYING_SURVIVING_SPOUSE):
        assert q.threshold[status] + q.phase_in_range[status] == 247_300


def test_amt_mfs_uses_half_the_28_percent_breakpoint(federal_2025):
    """MFS, standard deduction 15,750, taxable 252,750:
    AMTI 268,500; exemption 68,500 (no phase-out below 626,350)
    base 200,000 → 26% × 119,550 (31,083) + 28% × 80,450 (22,526) = 53,609."""
    _, tmt = amt_additional(Money(252_750), ZERO, "standard", Money(15_750), ZERO,
                            F.MARRIED_FILING_SEPARATELY, federal_2025.amt,
                            federal_2025.preferential_brackets[F.MARRIED_FILING_SEPARATELY],
                            ZERO)
    assert tmt == Money(53_609)


def test_obbba_2025_values(federal_2025):
    """Rev. Proc. 2025-32 §3.01 and §2.03; Schedule A instructions (2025)."""
    sd = federal_2025.standard_deduction
    assert (sd.single, sd.married_filing_jointly, sd.head_of_household) == (15_750, 31_500, 23_625)
    assert federal_2025.credits.child_tax_credit.amount_per_child == 2_200
    cap = federal_2025.itemized.salt_cap
    assert (cap.amount, cap.mfs_amount) == (40_000, 20_000)
    assert cap.phasedown.threshold.amount == 500_000
    assert federal_2025.estimated_payments.due_dates[1] == "06-16"
