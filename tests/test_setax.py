"""SE tax with W-2 wage-base coordination (spec §9.7) and taxable SS tiers."""

from decimal import Decimal

from ouch.engine.pipeline import _taxable_social_security
from ouch.engine.setax import additional_medicare, niit, self_employment_tax
from ouch.model.enums import FilingStatus
from ouch.model.money import Money, ZERO


def test_se_tax_no_wages(federal_2025):
    # base = 20,000 × 0.9235 = 18,470
    # SS = 18,470 × 12.4% = 2,290.28 ; Medicare = 18,470 × 2.9% = 535.63
    r = self_employment_tax(Money(20_000), ZERO, federal_2025)
    assert r.se_base == Money("18470")
    assert r.ss_portion.round_cent() == Money("2290.28")
    assert r.medicare_portion.round_cent() == Money("535.63")
    assert r.se_tax.round_cent() == Money("2825.91")
    assert r.se_deduction.round_cent() == Money("1412.96")


def test_se_ss_coordination_partial(federal_2025):
    # wage base 176,100; W-2 SS wages 170,000 → only 6,100 of SS room
    # SS = 6,100 × 12.4% = 756.40 ; Medicare = 18,470 × 2.9% = 535.63
    r = self_employment_tax(Money(20_000), Money(170_000), federal_2025)
    assert r.ss_portion.round_cent() == Money("756.40")
    assert r.se_tax.round_cent() == Money("1292.03")


def test_se_ss_coordination_full(federal_2025):
    # W-2 wages above the base: SS portion must be zero, never doubled.
    r = self_employment_tax(Money(50_000), Money(200_000), federal_2025)
    assert r.ss_portion == ZERO
    assert r.medicare_portion > ZERO


def test_se_negative_income_no_tax(federal_2025):
    r = self_employment_tax(Money(-5_000), ZERO, federal_2025)
    assert r.se_tax == ZERO and r.se_deduction == ZERO


def test_additional_medicare_mfj(federal_2025):
    # threshold MFJ 250,000; wages 281,000 → 31,000 × 0.9% = 279
    t = additional_medicare(Money(281_000), ZERO,
                            FilingStatus.MARRIED_FILING_JOINTLY, federal_2025)
    assert t.round_cent() == Money("279.00")


def test_niit(federal_2025):
    # single threshold 200,000; MAGI 210,000, NII 20,000
    # → 3.8% × min(20,000, 10,000) = 380
    t = niit(Money(20_000), Money(210_000), FilingStatus.SINGLE, federal_2025)
    assert t.round_cent() == Money("380.00")


def test_taxable_ss_below_base(federal_2025):
    t = _taxable_social_security(Money(10_000), ZERO, Money(20_000),
                                 FilingStatus.SINGLE, federal_2025)
    # provisional = 10,000 + 10,000 = 20,000 ≤ 25,000 → 0
    assert t == ZERO


def test_taxable_ss_middle_tier(federal_2025):
    # provisional = 25,000 + 15,000 = 40,000 → above 34,000:
    # lower = min(0.5×(34,000−25,000), 0.5×30,000) = 4,500
    # 0.85×(40,000−34,000) + 4,500 = 9,600 ; cap 0.85×30,000 = 25,500
    t = _taxable_social_security(Money(25_000), ZERO, Money(30_000),
                                 FilingStatus.SINGLE, federal_2025)
    assert t.round_cent() == Money("9600.00")


def test_taxable_ss_50pct_tier(federal_2025):
    # provisional = 20,000 + 10,000 = 30,000, between 25,000 and 34,000:
    # min(0.5×(30,000−25,000), 0.5×20,000) = 2,500
    t = _taxable_social_security(Money(20_000), ZERO, Money(20_000),
                                 FilingStatus.SINGLE, federal_2025)
    assert t.round_cent() == Money("2500.00")


def test_taxable_ss_capped_at_85pct(federal_2025):
    t = _taxable_social_security(Money(200_000), ZERO, Money(30_000),
                                 FilingStatus.SINGLE, federal_2025)
    assert t == Money(30_000) * Decimal("0.85")
