"""Independent derivation of the 2026 golden fixtures (rtrimble13/ouch#23).

This script does NOT import ouch. It walks the 2026 forms line by line with
figures typed from the primary sources cited next to each constant, and
writes each fixture's profile.toml, expected.json and SOURCE.md. Tax below
$100,000 and the earned income credit come from the published tables (the
2026 Tax Table and EIC Table in the draft 2026 Form 1040 instructions),
passed in as a JSON file of rows (tables_2026.json, from parse_tables.py),
not from a formula.

    python -I tests/golden_derive/derive.py \
        --tables tests/golden_derive/tables_2026.json --out tests/golden

Sources (2026 unless noted):
  RP     Rev. Proc. 2025-32 §4 (brackets, standard deduction, capital gain
         breakpoints, CTC, EIC, AMT, QBI thresholds)
  ES     2026 Form 1040-ES, What's New (Social Security wage base $184,500)
  I1040  draft 2026 Instructions for Form 1040: Tax Table, EIC Table,
         Qualified Dividends and Capital Gain Tax Worksheet (line 16),
         line 12f, Tax Computation Worksheet
  SA     draft 2026 Schedule A (line 5e SALT cap $40,400 / threshold
         $505,000); Instructions for Schedule A (2025) SALT worksheet: 30%
  S1A    draft 2026 Schedule 1-A Part V (seniors)
  SSE    draft 2026 Schedule SE (92.35%, 12.4%, 2.9%)
  S8812  2026 Schedule 8812
  F2441  draft 2026 Instructions for Form 2441, line 8 2026 Phaseout Schedule
  F6251  draft 2026 Form 6251 and instructions (exemption worksheet: 50%)
  F8801  draft 2026 Form 8801 Part II and instructions (line 22)
  F8959  draft 2026 Form 8959; F8960 draft 2026 Form 8960
  F8995  draft 2026 Forms 8995 / 8995-A
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from decimal import Decimal as D, ROUND_HALF_UP, ROUND_CEILING
from pathlib import Path

ZERO = D(0)
C = D("0.01")

S, J, MFS, HOH, QSS = ("single", "married_filing_jointly",
                       "married_filing_separately", "head_of_household",
                       "qualifying_surviving_spouse")

# --- RP §4.01 Tables 1–4: (over, base tax, rate); QSS uses Table 1 ---------
_T1 = [(0, "0", "0.10"), (24_800, "2480", "0.12"), (100_800, "11600", "0.22"),
       (211_400, "35932", "0.24"), (403_550, "82048", "0.32"),
       (512_450, "116896", "0.35"), (768_700, "206583.50", "0.37")]
_T2 = [(0, "0", "0.10"), (17_700, "1770", "0.12"), (67_450, "7740", "0.22"),
       (105_700, "16155", "0.24"), (201_750, "39207", "0.32"),
       (256_200, "56631", "0.35"), (640_600, "191171", "0.37")]
_T3 = [(0, "0", "0.10"), (12_400, "1240", "0.12"), (50_400, "5800", "0.22"),
       (105_700, "17966", "0.24"), (201_775, "41024", "0.32"),
       (256_225, "58448", "0.35"), (640_600, "192979.25", "0.37")]
_T4 = _T3[:6] + [(384_350, "103291.75", "0.37")]
SCHEDULE = {J: _T1, QSS: _T1, HOH: _T2, S: _T3, MFS: _T4}
TABLE_COLUMN = {S: 2, J: 3, QSS: 3, MFS: 4, HOH: 5}   # Tax Table columns

STANDARD = {J: 32_200, QSS: 32_200, HOH: 24_150, S: 16_100, MFS: 16_100}  # RP §4.14(1)
AGED_MARRIED, AGED_UNMARRIED = 1_650, 2_050                               # RP §4.14(3)
ZERO_RATE_MAX = {J: 98_900, QSS: 98_900, MFS: 49_450, HOH: 66_200, S: 49_450}      # RP §4.03
FIFTEEN_RATE_MAX = {J: 613_700, QSS: 613_700, MFS: 306_850, HOH: 579_600, S: 545_500}

SS_WAGE_BASE = 184_500                                # ES
SE_FACTOR, SS_RATE, MED_RATE = D("0.9235"), D("0.124"), D("0.029")   # SSE
ADDL_MED_THRESHOLD = {J: 250_000, MFS: 125_000, S: 200_000, HOH: 200_000, QSS: 200_000}  # F8959
NIIT_THRESHOLD = {J: 250_000, QSS: 250_000, MFS: 125_000, S: 200_000, HOH: 200_000}     # F8960

SALT_CAP, SALT_THRESHOLD, SALT_FLOOR, SALT_RATE = 40_400, 505_000, 10_000, D("0.30")    # SA
CHARITY_FLOOR = D("0.005")                            # I1040 What's New
LINE_12F = {J: 2_000}                                 # I1040 line 12f; others $1,000

SENIOR_AMOUNT, SENIOR_RATE = 6_000, D("0.06")         # S1A lines 38–41
SENIOR_THRESHOLD = {J: 150_000}                       # others $75,000
SENIOR_BORN_BEFORE = (1962, 1, 2)                     # S1A line 42a

CTC_PER_CHILD, ODC, ACTC_PER_CHILD = 2_200, 500, 1_700   # S8812 lines 5, 7, 16b
CTC_THRESHOLD = {J: 400_000}                          # others $200,000

EIC_INVESTMENT_LIMIT = 12_200                         # RP §4.06(2)

AMT_EXEMPTION = {J: 140_200, QSS: 140_200, MFS: 70_100, S: 90_100, HOH: 90_100}  # RP §4.10
AMT_PHASEOUT = {J: 1_000_000, QSS: 1_000_000, MFS: 500_000, S: 500_000, HOH: 500_000}
AMT_PHASEOUT_RATE = D("0.50")                         # F6251 exemption worksheet line 5
AMT_28_START = {MFS: 122_250}                         # others $244,500
AMT_28_SUBTRACT = {MFS: 2_445}                        # others $4,890

QBI_THRESHOLD = {J: 403_500, MFS: 201_775}            # RP §4.26; others $201,750
QBI_PHASE_IN_END = {J: 553_500, MFS: 276_775}         # RP §4.26; others $276,750

TIPS_CAP, OVERTIME_CAP = 25_000, 12_500               # S1A Parts II–III (OT $25,000 MFJ)
TIPS_OT_THRESHOLD = 150_000                           # S1A lines 23 ($300,000 MFJ)
CAR_CAP, CAR_THRESHOLD, CAR_STEP = 10_000, 100_000, 200   # S1A lines 30–35


def q(x: D) -> D:
    return x.quantize(C, ROUND_HALF_UP)


def m(x) -> str:
    return f"{q(D(x)):,.2f}"


def schedule_tax(x: D, status: str) -> D:
    over, base, rate = max((r for r in SCHEDULE[status] if x > r[0]),
                           key=lambda r: r[0], default=SCHEDULE[status][0])
    return D(base) + D(rate) * (x - over)


@dataclass
class Tables:
    tax: dict
    eic: dict

    def tax_on(self, x: D, status: str, log) -> D:
        """Tax Table below $100,000 (I1040 line 16); Tax Computation
        Worksheet (the RP schedule) at or above it."""
        if x <= 0:
            return ZERO
        if x >= 100_000:
            t = schedule_tax(x, status)
            log(f"  - tax on {m(x)} (Tax Computation Worksheet, {status}) = {m(t)}")
            return t
        lo = int(x // 50 * 50) if x >= 3_000 else None
        row = self.tax.get(str(lo))
        if row is None or not (row[0] <= x < row[1]):
            raise SystemExit(f"no Tax Table row for {x}")
        t = D(row[TABLE_COLUMN[status]])
        log(f"  - tax on {m(x)}: 2026 Tax Table row {row[0]:,}–{row[1]:,}, "
            f"{status} column = {t:,}")
        return t

    def eic_on(self, x: D, children: int, joint: bool) -> D:
        lo = 1 if x < 50 else int(x // 50 * 50)
        row = self.eic.get(str(lo))
        if row is None:
            if x >= max(int(k) for k in self.eic):
                return ZERO   # past the end of the table: no credit
            raise SystemExit(f"no EIC Table row for {x}")
        cell = row[2 + (4 if joint else 0) + children]
        if cell < 0:
            raise SystemExit(f"EIC Table footnote cell at {x}: read it by hand")
        return D(cell)


@dataclass
class Case:
    name: str
    title: str
    status: str
    covers: str
    wages_tp: D = ZERO
    wages_sp: D = ZERO
    sched_c: D = ZERO
    c_owner: str = "taxpayer"
    interest: D = ZERO
    ord_div: D = ZERO
    qual_div: D = ZERO
    st: D = ZERO
    lt: D = ZERO
    cap_carry: D = ZERO
    pension: D = ZERO
    ira: D = ZERO
    tp_birth: str | None = None
    sp_birth: str | None = None
    spouse: bool = False
    kids: tuple = ()                       # birth dates
    care: D = ZERO
    salt_income: D = ZERO
    salt_property: D = ZERO
    mortgage: D = ZERO
    charity_cash: D = ZERO
    mtc_carry: D = ZERO
    tips: D = ZERO
    overtime: D = ZERO
    car_interest: D = ZERO
    state: str = "TX"
    locality: str = ""
    withholding: D = ZERO
    notes: str = ""

    def __post_init__(self):
        for k, v in list(vars(self).items()):
            if isinstance(v, int) and not isinstance(v, bool):
                setattr(self, k, D(v))


def born_65(birth: str | None) -> bool:
    if not birth:
        return False
    y, mo, d = (int(p) for p in birth.split("-"))
    return (y, mo, d) < SENIOR_BORN_BEFORE


def age_end_2026(birth: str) -> int:
    y, mo, d = (int(p) for p in birth.split("-"))
    return 2026 - y   # Dec 31 birthday arithmetic is enough for children here


def derive(c: Case, tables: Tables):
    L: list[str] = []
    log = L.append
    st = c.status
    joint = st == J

    log("### Income (Form 1040 lines 1–11)")
    wages = c.wages_tp + c.wages_sp
    if wages:
        log(f"- Line 1a wages: {m(wages)}"
            + (f" (taxpayer {m(c.wages_tp)}, spouse {m(c.wages_sp)})" if c.wages_sp else ""))
    if c.interest:
        log(f"- Line 2b taxable interest: {m(c.interest)}")
    if c.ord_div:
        log(f"- Line 3a qualified dividends {m(c.qual_div)}; line 3b ordinary dividends {m(c.ord_div)}")

    # Schedule SE
    se_tax = half_se = nese = ZERO
    if c.sched_c > 0:
        owner_w2 = c.wages_sp if c.c_owner == "spouse" else c.wages_tp
        nese = c.sched_c * SE_FACTOR
        ss_room = max(ZERO, D(SS_WAGE_BASE) - owner_w2)
        ss_base = min(nese, ss_room)
        ss = ss_base * SS_RATE
        med = nese * MED_RATE
        se_tax = ss + med
        half_se = se_tax / 2
        log(f"- Schedule SE ({c.c_owner}): net earnings 92.35% × {m(c.sched_c)} = {m(nese)}")
        log(f"  - Social Security part: room under the $184,500 wage base = "
            f"184,500 − {c.c_owner}'s W-2 {m(owner_w2)} = {m(ss_room)}; "
            f"12.4% × {m(ss_base)} = {m(ss)}")
        log(f"  - Medicare part: 2.9% × {m(nese)} = {m(med)}")
        log(f"  - SE tax {m(se_tax)}; deductible half (Schedule 1 line 15) {m(half_se)}")
    elif c.sched_c < 0:
        log(f"- Schedule C loss {m(c.sched_c)}: no SE tax (net earnings below $400)")

    # Schedule D
    cap_line7 = ZERO
    net_gain_pref = ZERO
    if c.st or c.lt or c.cap_carry:
        l7 = c.st
        l15 = c.lt - c.cap_carry
        l16 = l7 + l15
        log(f"- Schedule D: line 7 short-term {m(l7)}; line 15 long-term {m(c.lt)}"
            + (f" − carryover {m(c.cap_carry)} = {m(l15)}" if c.cap_carry else ""))
        log(f"  - line 16 = {m(l16)}")
        if l16 < 0:
            cap_line7 = max(l16, D(-3_000))
            log(f"  - line 21 loss allowed: {m(cap_line7)} (limit $3,000); "
                f"carryover to 2027 = {m(-l16 + cap_line7)}")
        else:
            cap_line7 = l16
            net_gain_pref = max(ZERO, min(l15, l16))
        log(f"- Line 7a capital gain or (loss): {m(cap_line7)}")
    if c.sched_c:
        log(f"- Schedule 1 line 3 business income: {m(c.sched_c)}")
    if c.pension:
        log(f"- Line 5b pensions: {m(c.pension)}")
    if c.ira:
        log(f"- Line 4b IRA distributions: {m(c.ira)}")
    total_income = (wages + c.interest + c.ord_div + cap_line7 + c.sched_c
                    + c.pension + c.ira)
    log(f"- **Line 9 total income: {m(total_income)}**")
    agi = total_income - half_se
    if half_se:
        log(f"- Line 10 adjustments: {m(half_se)} (half of SE tax)")
    log(f"- **Line 11 AGI: {m(agi)}**")

    # Line 12: standard or itemized
    log("")
    log("### Deductions (lines 12–14)")
    aged = sum(born_65(b) for b in (c.tp_birth, c.sp_birth if c.spouse else None))
    per = AGED_MARRIED if st in (J, MFS, QSS) else AGED_UNMARRIED
    std = D(STANDARD[st] + aged * per)
    log(f"- Standard deduction: {STANDARD[st]:,}"
        + (f" + {aged} × {per:,} (65 or older) = {m(std)}" if aged else ""))
    salt_paid = c.salt_income + c.salt_property
    itemized = ZERO
    salt = ZERO
    if salt_paid or c.mortgage or c.charity_cash:
        cap = D(SALT_CAP)
        if agi > SALT_THRESHOLD:
            cap = max(D(SALT_FLOOR), cap - SALT_RATE * (agi - SALT_THRESHOLD))
            log(f"- SALT cap: AGI {m(agi)} over $505,000 → "
                f"max(10,000, 40,400 − 30% × {m(agi - SALT_THRESHOLD)}) = {m(cap)}")
        salt = min(salt_paid, cap)
        log(f"- Schedule A line 5d SALT paid {m(salt_paid)} → line 5e {m(salt)}")
        floor = CHARITY_FLOOR * agi
        gifts = max(ZERO, c.charity_cash - floor)
        if c.mortgage:
            log(f"- Schedule A line 8a mortgage interest {m(c.mortgage)}")
        if c.charity_cash:
            log(f"- Charity: cash {m(c.charity_cash)} − 0.5% × AGI ({m(floor)}) = {m(gifts)}")
        itemized = salt + c.mortgage + gifts
        log(f"- Schedule A line 17 total itemized: {m(itemized)}")
    line_12f = min(c.charity_cash, D(LINE_12F.get(st, 1_000)))
    if itemized > std + line_12f:
        mode, ded, line_12f = "itemized", itemized, ZERO
        log(f"- Itemized {m(itemized)} beats standard {m(std)}"
            + (f" + line 12f" if c.charity_cash else "") + " → itemize")
    else:
        mode, ded = "standard", std
        if itemized:
            log(f"- Itemized {m(itemized)} ≤ standard {m(std)} + line 12f {m(line_12f)} → standard")
        if line_12f:
            log(f"- Line 12f non-itemizer cash gifts: {m(line_12f)}")
    log(f"- **Line 12e: {m(ded)} ({mode})**")

    # Schedule 1-A Part V
    senior = ZERO
    senior_only = ZERO
    overtime_ded = ZERO
    n_sen = sum(born_65(b) for b in (c.tp_birth, c.sp_birth if joint else None))
    if n_sen and st != MFS:
        thr = D(SENIOR_THRESHOLD.get(st, 75_000))
        l39 = max(ZERO, agi - thr)
        l41 = max(ZERO, SENIOR_AMOUNT - SENIOR_RATE * l39)
        senior = senior_only = l41 * n_sen
        log(f"- Schedule 1-A Part V: line 39 = {m(agi)} − {m(thr)} = {m(l39)}; "
            f"line 41 = 6,000 − 6% × {m(l39)} = {m(l41)}; × {n_sen} = **{m(senior)}** (line 13a)")

    # Schedule 1-A Parts II–IV (taxpayer only, single filers in these fixtures)
    if c.tips or c.overtime or c.car_interest:
        assert st != J and agi <= TIPS_OT_THRESHOLD
        tips = min(c.tips, D(TIPS_CAP))
        ot = min(c.overtime, D(OVERTIME_CAP))
        car = min(c.car_interest, D(CAR_CAP))
        if agi > CAR_THRESHOLD:
            n = ((agi - CAR_THRESHOLD) / 1000).to_integral_value(ROUND_CEILING)
            car = max(ZERO, car - n * CAR_STEP)
            log(f"- Schedule 1-A Part IV: line 33 = {m(agi)} − 100,000 = "
                f"{m(agi - CAR_THRESHOLD)}; line 34 rounded up = {n}; "
                f"line 36 = {m(min(c.car_interest, D(CAR_CAP)))} − {n} × 200 = {m(car)}")
        log(f"- Schedule 1-A: tips {m(tips)} (Part II, MAGI under 150,000); overtime "
            f"{m(ot)} (Part III); car-loan interest {m(car)}")
        senior += tips + ot + car
        overtime_ded = ot
        log(f"- **Schedule 1-A line 44 (Form 1040 line 13a): {m(senior)}**")

    # QBI
    qbi = ZERO
    ti_before = agi - ded - line_12f - senior
    if c.sched_c > 0:
        qbi_income = c.sched_c - half_se
        comp = D("0.20") * qbi_income
        thr = D(QBI_THRESHOLD.get(st, 201_750))
        rng = D(QBI_PHASE_IN_END.get(st, 276_750)) - thr
        log(f"- QBI: {m(c.sched_c)} − deductible SE tax {m(half_se)} = {m(qbi_income)}; "
            f"20% = {m(comp)}")
        log(f"  - taxable income before QBI = {m(agi)} − {m(ded)}"
            + (f" − {m(line_12f)}" if line_12f else "")
            + (f" − {m(senior)}" if senior else "") + f" = {m(ti_before)}")
        if ti_before > thr:
            pct = min(D(1), (ti_before - thr) / rng)
            reduction = comp * pct          # W-2 wages and UBIA are zero
            log(f"  - Form 8995-A Part III: over the {m(thr)} threshold by "
                f"{m(ti_before - thr)} → {pct:.6f} of the {m(rng)} phase-in range; "
                f"W-2 wages/UBIA limit 0 → reduction {m(reduction)}; "
                f"component {m(comp - reduction)}")
            comp -= reduction
        limit = D("0.20") * (ti_before - net_gain_pref - c.qual_div)
        qbi = min(comp, limit)
        log(f"  - income limit 20% × ({m(ti_before)} − net capital gain "
            f"{m(net_gain_pref + c.qual_div)}) = {m(limit)} → **QBI deduction {m(qbi)}** (line 13b)")
    elif c.sched_c < 0:
        log(f"- QBI: a {m(c.sched_c)} business loss → deduction 0; the loss "
            "carries forward as a qualified business loss")
    taxable = max(ZERO, ti_before - qbi)
    log(f"- **Line 15 taxable income: {m(taxable)}**")

    # Line 16
    log("")
    log("### Tax (line 16)")
    pref = c.qual_div + net_gain_pref
    if pref > 0:
        l1, l4 = taxable, pref
        l5 = max(ZERO, l1 - l4)
        l6 = D(ZERO_RATE_MAX[st])
        l7 = min(l1, l6); l8 = min(l5, l7); l9 = l7 - l8
        l10 = min(l1, l4); l12 = l10 - l9
        l13 = D(FIFTEEN_RATE_MAX[st]); l14 = min(l1, l13)
        l15 = l5 + l9; l16 = max(ZERO, l14 - l15); l17 = min(l12, l16)
        l18 = l17 * D("0.15"); l19 = l9 + l17; l20 = l10 - l19; l21 = l20 * D("0.20")
        log("Qualified Dividends and Capital Gain Tax Worksheet (I1040):")
        log(f"- line 1 {m(l1)}; line 4 {m(l4)}; line 5 {m(l5)}")
        log(f"- line 6 {m(l6)}; line 9 taxed at 0%: {m(l9)}")
        log(f"- line 17 at 15%: {m(l17)} → line 18 {m(l18)}")
        log(f"- line 20 at 20%: {m(l20)} → line 21 {m(l21)}")
        l22 = tables.tax_on(l5, st, log)
        log(f"- line 22 (tax on line 5): {m(l22)}")
        l23 = l18 + l21 + l22
        l24 = tables.tax_on(l1, st, log)
        log(f"- line 23 = {m(l23)}; line 24 (tax on line 1) = {m(l24)}")
        tax = min(l23, l24)
        log(f"- **line 25 = smaller of 23 and 24 = {m(tax)}**")
        tax_ord, tax_pref = l22, tax - l22
    else:
        tax = tables.tax_on(taxable, st, log)
        tax_ord, tax_pref = tax, ZERO
        log(f"- **Line 16: {m(tax)}**")

    # Form 6251
    log("")
    log("### Form 6251 (AMT)")
    l1b = taxable + senior_only
    l2a = std if mode == "standard" else salt
    amti = l1b + l2a
    log(f"- line 1b = taxable income {m(taxable)}"
        + (f" + Schedule 1-A line 43 senior deduction {m(senior_only)}" if senior_only else "")
        + f" = {m(l1b)}")
    log(f"- line 2a ({'line 12e standard deduction' if mode == 'standard' else 'Schedule A line 7 taxes'}): {m(l2a)}")
    log(f"- line 4 AMTI: {m(amti)}")
    ex = max(ZERO, D(AMT_EXEMPTION[st]) - AMT_PHASEOUT_RATE * max(ZERO, amti - AMT_PHASEOUT[st]))
    log(f"- line 5 exemption: {m(ex)}"
        + (f" (= {AMT_EXEMPTION[st]:,} − 50% × {m(amti - AMT_PHASEOUT[st])})" if amti > AMT_PHASEOUT[st] else ""))
    base = max(ZERO, amti - ex)
    start = D(AMT_28_START.get(st, 244_500)); sub = D(AMT_28_SUBTRACT.get(st, 4_890))

    def amt_rate(x):
        return x * D("0.26") if x <= start else x * D("0.28") - sub
    log(f"- line 6: {m(base)}")
    if pref > 0 and base > 0:
        p12, p13 = base, pref
        p16 = min(p12, p13); p17 = p12 - p16; p18 = amt_rate(p17)
        p19 = D(ZERO_RATE_MAX[st]); p20 = max(ZERO, taxable - pref)
        p21 = max(ZERO, p19 - p20); p22 = min(p12, p13); p23 = min(p21, p22); p24 = p22 - p23
        p25 = D(FIFTEEN_RATE_MAX[st]); p28 = p21 + p20; p29 = max(ZERO, p25 - p28)
        p30 = min(p24, p29); p31 = p30 * D("0.15"); p32 = p23 + p30
        p33 = p22 - p32; p34 = p33 * D("0.20")
        p38 = p18 + p31 + p34; p39 = amt_rate(p12); tmt = min(p38, p39)
        log("- Part III: line 17 ordinary AMT base "
            f"{m(p17)} → line 18 {m(p18)}")
        log(f"  - line 20 = QDCGT worksheet line 5 (regular tax) {m(p20)}; "
            f"line 21 = {m(p21)}; line 23 at 0%: {m(p23)}")
        log(f"  - line 29 = {m(p25)} − (line 21 + line 27 = {m(p28)}) = {m(p29)}; "
            f"line 30 at 15%: {m(p30)} → {m(p31)}")
        log(f"  - line 33 at 20%: {m(p33)} → {m(p34)}")
        log(f"  - line 38 = {m(p38)}; line 39 (all at AMT rates) = {m(p39)}; "
            f"line 40 = {m(tmt)}")
    else:
        tmt = amt_rate(base) if base > 0 else ZERO
        log(f"- line 7: {'26%' if base <= start else '28% − ' + m(sub)} → {m(tmt)}")
    log(f"- line 9 TMT {m(tmt)}; line 10 regular tax {m(tax)}")
    amt = max(ZERO, tmt - tax)
    log(f"- **line 11 AMT: {m(amt)}**")

    # Credits
    log("")
    log("### Credits")
    remaining = tax + amt
    care = ZERO
    kids_ages = [age_end_2026(k) for k in c.kids]
    if c.care:
        n_care = sum(a < 13 for a in kids_ages)
        cap = D(3_000 if n_care == 1 else 6_000)
        earned_min = min(c.wages_tp, c.wages_sp) if joint else c.wages_tp
        base_c = min(c.care, cap, earned_min)
        rate = care_rate(agi, st)
        care = min(base_c * rate, remaining)
        log(f"- Form 2441: expenses {m(c.care)}, limit {m(cap)} ({n_care} children), "
            f"lower earner {m(earned_min)} → {m(base_c)}; 2026 Phaseout Schedule rate "
            f"at AGI {m(agi)}: {rate} → **{m(care)}**")
        remaining -= care
    ctc = actc = ZERO
    n_ctc = sum(a < 17 for a in kids_ages)
    if n_ctc:
        l8 = D(n_ctc * CTC_PER_CHILD)
        thr = D(CTC_THRESHOLD.get(st, 200_000))
        excess = max(ZERO, agi - thr)
        l10 = (excess / 1000).to_integral_value(ROUND_CEILING) * 1000
        l12 = max(ZERO, l8 - l10 * D("0.05"))
        l13 = max(ZERO, remaining)
        ctc = min(l12, l13)
        log(f"- Schedule 8812: line 8 = {n_ctc} × 2,200 = {m(l8)}; line 11 = {m(l10 * D('0.05'))}; "
            f"line 12 = {m(l12)}; line 13 (Credit Limit Worksheet A) = {m(l13)}; "
            f"**line 14 = {m(ctc)}**")
        remaining -= ctc
        l16a = l12 - ctc
        if l16a > 0:
            l16b = D(n_ctc * ACTC_PER_CHILD)
            l17 = min(l16a, l16b)
            earned = wages + (nese - half_se if c.sched_c > 0 else ZERO)
            l20 = max(ZERO, earned - 2_500) * D("0.15")
            actc = min(l17, l20)
            log(f"  - line 16a {m(l16a)}; 16b {m(l16b)}; 17 {m(l17)}; "
                f"line 20 = 15% × ({m(earned)} − 2,500) = {m(l20)}")
            if l16b >= 5_100 and l20 < l17:
                ss_med = wages * D("0.0765")
                l25 = max(ZERO, ss_med - eic_amount(c, agi, wages, tables, None))
                actc = min(l17, max(l20, l25))
                log(f"  - Part II-B: withheld SS + Medicare {m(ss_med)} less EIC → line 25 {m(l25)}")
            log(f"  - **line 27 ACTC: {m(actc)}**")
    mtc = ZERO
    if c.mtc_carry:
        l22 = tax - ctc - care
        l24 = max(ZERO, l22 - tmt)
        mtc = min(c.mtc_carry, l24) if amt == 0 else ZERO
        log(f"- Form 8801: line 21 carryforward {m(c.mtc_carry)}; line 22 = line 16 "
            f"{m(tax)} − credits {m(ctc + care)} = {m(l22)}; line 23 TMT {m(tmt)}; "
            f"line 24 {m(l24)}; **line 25 credit {m(mtc)}**; carryforward to 2027 "
            f"{m(c.mtc_carry - mtc)}")
        remaining -= mtc
    nonref = care + ctc + mtc
    eic = eic_amount(c, agi, wages, tables, log) if (wages and not c.sched_c) else ZERO
    if not (nonref or eic or actc):
        log("- none")

    # Other taxes
    log("")
    log("### Other taxes (Schedule 2)")
    thr = D(ADDL_MED_THRESHOLD[st])
    addl_w = max(ZERO, wages - thr) * D("0.009")
    addl_se = ZERO
    if nese:
        addl_se = max(ZERO, nese - max(ZERO, thr - wages)) * D("0.009")
    addl = addl_w + addl_se
    if addl:
        log(f"- Form 8959: Part I 0.9% × ({m(wages)} − {m(thr)}) = {m(addl_w)}"
            + (f"; Part II 0.9% × ({m(nese)} − max(0, {m(thr)} − {m(wages)})) = {m(addl_se)}" if nese else "")
            + f" → **{m(addl)}**")
    nii = c.interest + c.ord_div + max(cap_line7, D(-3_000))
    nthr = D(NIIT_THRESHOLD[st])
    niit = ZERO
    if agi > nthr and nii > 0:
        niit = min(nii, agi - nthr) * D("0.038")
        log(f"- Form 8960: NII {m(nii)}; MAGI over {m(nthr)} = {m(agi - nthr)}; "
            f"3.8% × smaller = **{m(niit)}**")
    if se_tax:
        log(f"- Schedule SE tax: {m(se_tax)}")
    if not (addl or niit or se_tax):
        log("- none")

    line24 = tax + amt - nonref + se_tax + addl + niit
    refundable = eic + actc
    fed_total = line24 - refundable
    log("")
    log("### Totals")
    log(f"- Line 24 total tax = {m(tax)} + {m(amt)} − {m(nonref)} + {m(se_tax + addl + niit)} = {m(line24)}")
    if refundable:
        log(f"- Refundable credits (lines 27a + 28): {m(refundable)}")
    log(f"- ouch `federal_total_tax` (line 24 less refundable credits): **{m(fed_total)}**")
    log(f"- Payments (withholding): {m(c.withholding)} → balance {m(fed_total - c.withholding)}")

    state_out, local_out, state_total = derive_state(
        c, agi=agi, fed_taxable=taxable, fed_deduction=ded, qbi=qbi,
        overtime=overtime_ded, log=log)
    all_tax = fed_total + state_total
    if c.state != "TX":
        log(f"- **Total tax, all jurisdictions: {m(all_tax)}**; balance {m(all_tax - c.withholding)}")

    expected = {
        "total_income": total_income, "agi": agi, "deduction_taken": ded,
        "deduction_mode": mode, "qbi_deduction": qbi,
        "schedule_1a_deduction": senior,
        "nonitemizer_charitable_deduction": line_12f,
        "taxable_income": taxable, "tax_ordinary": tax_ord,
        "tax_preferential": tax_pref, "amt_additional": amt, "se_tax": se_tax,
        "additional_medicare": addl, "niit": niit,
        "credits_nonrefundable": nonref, "credits_refundable": refundable,
        "federal_total_tax": fed_total, "total_tax_all_jurisdictions": all_tax,
        "total_payments": c.withholding,
        "balance_due_or_refund": all_tax - c.withholding,
    }
    out = {k: (v if isinstance(v, str) else f"{q(v):.2f}") for k, v in expected.items()}
    if state_out is not None:
        out["state"] = {k: (v if isinstance(v, str) else f"{q(v):.2f}") for k, v in state_out.items()}
    if local_out is not None:
        out["local"] = {k: (v if isinstance(v, str) else f"{q(v):.2f}") for k, v in local_out.items()}
    return out, L


# --- States (2026 files). Sources:
#   CA  FTB 2026 Form 540-ES Instructions (2026 worksheet: 2025 tax table,
#       standard deduction $5,706 / $11,412, 2025 exemption credits); FTB 2025
#       Personal Income Tax Booklet (Schedules X/Y/Z p. 75; lines 7–10, 32).
#   NY  NY DTF IT-2105-I (2026): standard deduction table, dependent
#       exemptions $1,000, 2026 NYS and NYC tax rates (p. 10), NYC school tax
#       credits (lines 20–21).
#   CO  CO DOR Individual Income Tax Guide (rev. January 2026): 4.4% (2025,
#       carried to 2026), additions in Part 3.
CA_X = [(0, "0", "0.01"), (11_079, "110.79", "0.02"), (26_264, "414.49", "0.04"),
        (41_452, "1022.01", "0.06"), (57_542, "1987.41", "0.08"),
        (72_724, "3201.97", "0.093"), (371_479, "30986.19", "0.103"),
        (445_771, "38638.27", "0.113"), (742_953, "72219.84", "0.123")]
CA_Y = [(0, "0", "0.01"), (22_158, "221.58", "0.02"), (52_528, "828.98", "0.04"),
        (82_904, "2044.02", "0.06"), (115_084, "3974.82", "0.08"),
        (145_448, "6403.94", "0.093"), (742_958, "61972.37", "0.103"),
        (891_542, "77276.52", "0.113"), (1_485_906, "144439.65", "0.123")]
CA_STD = {S: 5_706, MFS: 5_706, J: 11_412, HOH: 11_412, QSS: 11_412}
CA_AGI_LIMIT = {S: 252_203, MFS: 252_203, J: 504_411, QSS: 504_411, HOH: 378_310}
NY_STD = {S: 8_000, MFS: 8_000, J: 16_050, QSS: 16_050, HOH: 11_200}
NY_SINGLE_2026 = [(0, "0", "0.039"), (8_500, "332", "0.044"), (11_700, "473", "0.0515"),
                  (13_900, "586", "0.054"), (80_650, "4191", "0.059"),
                  (215_400, "12141", "0.0685")]
NYC_SINGLE = [(0, "0", "0.03078"), (12_000, "369", "0.03762"), (25_000, "858", "0.03819"),
              (50_000, "1813", "0.03876")]


def sched(x: D, rows) -> D:
    over, base, rate = max((r for r in rows if x > r[0]), key=lambda r: r[0])
    return D(base) + D(rate) * (x - over)


def derive_state(c: Case, *, agi, fed_taxable, fed_deduction, qbi, overtime, log):
    st = c.status
    if c.state == "TX":
        return None, None, ZERO
    log("")
    if c.state == "CA":
        log("### California (Form 540)")
        std = D(CA_STD[st])
        taxable = agi - std
        assert taxable >= 100_000, "below $100,000 California uses its tax table"
        tax = sched(taxable, CA_Y if st in (J, QSS) else CA_X)
        log(f"- Line 17 California AGI = federal AGI {m(agi)}; line 18 standard deduction {m(std)}; "
            f"line 19 taxable {m(taxable)}")
        log(f"- Line 31 tax (Schedule {'Y' if st in (J, QSS) else 'X'}): {m(tax)}")
        n_filer = 2 if st in (J, QSS) else 1
        n_dep = len(c.kids)
        filer, dep = D(153 * n_filer), D(475 * n_dep)
        excess = agi - CA_AGI_LIMIT[st]
        if excess > 0:
            steps = (excess / (1_250 if st == MFS else 2_500)).to_integral_value(ROUND_CEILING)
            e = steps * 6
            filer, dep = max(ZERO, filer - e * n_filer), max(ZERO, dep - e * n_dep)
            log(f"- AGI Limitation Worksheet: {m(excess)} over {CA_AGI_LIMIT[st]:,} → "
                f"{steps} steps × $6 = {m(e)} per credit")
        credits = filer + dep
        log(f"- Line 32 exemption credits: {n_filer} × 153 + {n_dep} × 475 after the "
            f"limitation = {m(credits)}")
        state_tax = max(ZERO, tax - credits)
        log(f"- **Line 33 / 48 California tax: {m(state_tax)}**")
        return ({"code": "CA", "agi": agi, "deduction": std, "taxable": taxable,
                 "tax": state_tax}, None, state_tax)
    if c.state == "NY":
        assert st == S and not c.kids and agi <= 107_650
        log("### New York State (IT-2105 worksheet, 2026)")
        std = D(NY_STD[st])
        taxable = agi - std
        assert taxable >= 65_000, "below $65,000 New York uses its tax table"
        tax = sched(taxable, NY_SINGLE_2026)
        log(f"- New York AGI = federal AGI {m(agi)} (≤ $107,650, so the rate schedule "
            f"applies directly); standard deduction {m(std)}; taxable {m(taxable)}")
        log(f"- 2026 New York State tax rates, single: **{m(tax)}**")
        local = None
        city = ZERO
        if c.locality == "NYC":
            assert taxable >= 65_000
            city_tax = sched(taxable, NYC_SINGLE)
            fixed = D(63) if agi <= 250_000 else ZERO
            rr = ((D(21) + D("0.00228") * (taxable - 12_000)) if taxable > 12_000
                  else D("0.00171") * taxable) if agi <= 500_000 else ZERO
            city = max(ZERO, city_tax - fixed - rr)
            log(f"- New York City tax on {m(taxable)} (2026 NYC tax rates, single): {m(city_tax)}")
            log(f"- School tax credit, fixed amount (income ≤ $250,000): {m(fixed)}; rate "
                f"reduction amount 21 + 0.228% × ({m(taxable)} − 12,000) = {m(rr)}")
            log(f"- **New York City tax after the school tax credits: {m(city)}**")
            local = {"name": "NYC", "taxable": taxable, "tax": city}
        return ({"code": "NY", "agi": agi, "deduction": std, "taxable": taxable,
                 "tax": tax}, local, tax + city)
    if c.state == "CO":
        log("### Colorado (DR 0104, 2026 rules)")
        adds = []
        if overtime:
            adds.append(("overtime deduction addback", overtime))
        if agi > 300_000:
            lim = D(2_000 if st == J else 1_000)
            if fed_deduction > lim:
                adds.append((f"deduction above the {m(lim)} limit (AGI over $300,000)",
                             fed_deduction - lim))
        if qbi and agi > (1_000_000 if st == J else 500_000):
            adds.append(("QBI deduction addback", qbi))
        total_add = sum((a for _, a in adds), ZERO)
        taxable = fed_taxable + total_add
        assert taxable >= 50_000, "below $50,000 Colorado uses its tax table"
        tax = taxable * D("0.044")
        log(f"- Federal taxable income {m(fed_taxable)}")
        for label, a in adds:
            log(f"- Addition: {label}: {m(a)}")
        log(f"- Colorado taxable income {m(taxable)} × 4.4% = **{m(tax)}**")
        return ({"code": "CO", "agi": taxable, "deduction": ZERO, "taxable": taxable,
                 "tax": tax}, None, tax)
    raise SystemExit(f"no state derivation for {c.state}")


def care_rate(agi: D, st: str) -> D:
    """F2441 line 8, 2026 Phaseout Schedule."""
    def steps(over, width):
        return int(((agi - over) / width).to_integral_value(ROUND_CEILING)) if agi > over else 0
    rate = max(D("0.35"), D("0.50") - D("0.01") * steps(15_000, 2_000))
    hi, width = (150_000, 4_000) if st == J else (75_000, 2_000)
    rate = max(D("0.20"), rate - D("0.01") * steps(hi, width))
    return rate


def eic_amount(c: Case, agi: D, earned: D, tables: Tables, log) -> D:
    n = min(3, sum(age_end_2026(k) < 19 for k in c.kids))
    joint = c.status == J
    if c.status == MFS:
        return ZERO
    inv = c.interest + c.ord_div + max(ZERO, c.st + c.lt - c.cap_carry)
    if inv > EIC_INVESTMENT_LIMIT:
        return ZERO
    by_earned = tables.eic_on(earned, n, joint)
    credit = by_earned
    thr = (31_160 if n else 18_140) if joint else (23_890 if n else 10_860)
    if agi != earned and agi >= thr:
        credit = min(by_earned, tables.eic_on(agi, n, joint))
    if log is not None and credit:
        kids = f"{n} child" if n == 1 else f"{n} children"
        log(f"- EIC (EIC Table, {kids}, {'MFJ' if joint else 'other'} column): "
            f"earned income {m(earned)} → {credit:,}; AGI {m(agi)} → "
            f"**{credit:,}** (line 27a)")
    return credit


# ----------------------------------------------------------------------------

def toml_profile(c: Case) -> str:
    out = ["schema_version = 2", "tax_year = 2026", "", "[taxpayer]",
           f'filing_status = "{c.status}"', f'state = "{c.state}"']
    if c.locality:
        out.append(f'locality = "{c.locality}"')
    if c.tp_birth:
        out.append(f'birth_date = {c.tp_birth}')
    if c.spouse:
        out += ["", "[spouse]"]
        if c.sp_birth:
            out.append(f"birth_date = {c.sp_birth}")
    for i, b in enumerate(c.kids):
        out += ["", "[[dependents]]", f'name = "child{i + 1}"', f"birth_date = {b}",
                'relationship = "child"']

    def sec(name, items):
        items = [(k, v) for k, v in items if v]
        if items:
            out.extend(["", f"[{name}]"] + [f"{k} = {fmt(v)}" for k, v in items])
    sec("income.wages", [("taxpayer_w2", c.wages_tp), ("spouse_w2", c.wages_sp),
                         ("taxpayer_qualified_tips", c.tips),
                         ("taxpayer_qualified_overtime", c.overtime)])
    sec("income.investment", [("interest", c.interest), ("ordinary_dividends", c.ord_div),
                              ("qualified_dividends", c.qual_div),
                              ("short_term_gains", c.st), ("long_term_gains", c.lt),
                              ("capital_loss_carryforward", c.cap_carry)])
    if c.sched_c:
        out += ["", "[income.business]"]
        if c.c_owner != "taxpayer":
            out.append(f'owner = "{c.c_owner}"')
        out += [f"schedule_c_net = {fmt(c.sched_c)}",
                f"qbi_eligible_income = {fmt(c.sched_c)}"]
    sec("income.retirement", [("pension", c.pension), ("ira_distributions", c.ira)])
    sec("deductions.itemized", [("state_local_income_tax", c.salt_income),
                                ("real_estate_tax", c.salt_property),
                                ("mortgage_interest", c.mortgage),
                                ("charitable_cash", c.charity_cash)])
    sec("deductions", [("car_loan_interest", c.car_interest)])
    sec("expenses", [("dependent_care", c.care)])
    sec("carryovers", [("amt_credit", c.mtc_carry)])
    sec("payments.withholding", [("federal_ytd", c.withholding)])
    return "\n".join(out) + "\n"


def fmt(v) -> str:
    v = D(v)
    return f'"{v}"' if v != v.to_integral_value() else str(int(v))


def source_md(c: Case, lines: list[str]) -> str:
    return "\n".join([
        f"# {c.title}", "",
        f"**Covers:** {c.covers}", "",
        "## Derivation basis", "",
        "Worked line by line through the 2026 forms with figures from Rev. Proc.",
        "2025-32 §4 and the 2026 IRS forms and draft instructions cited in",
        "`tests/golden_derive/derive.py`, which does not import ouch. Tax on",
        "taxable income below $100,000 is read from the 2026 Tax Table and the",
        "earned income credit from the 2026 EIC Table (draft 2026 Instructions",
        "for Form 1040), not computed by formula; the harness compares money",
        "fields to the dollar (spec §19). **Not** produced by running `ouch`",
        "(spec §16.2).", "",
        *( [c.notes, ""] if c.notes else [] ),
        "## Computation", "", *lines, "",
    ])


# ----------------------------------------------------------------------------
# The fixtures. Inputs below $100,000 of taxable income are picked so the
# figure lands at the midpoint of its $50 Tax Table row, where the table and
# the rate schedule agree to within rounding.

CASES = [
    Case("2026_single_wages", "Single, wages only", S,
         "filing status single; Tax Table", wages_tp=60_025, withholding=5_500),
    Case("2026_mfj_wages", "Married filing jointly, two earners", J,
         "filing status MFJ; Tax Computation Worksheet", wages_tp=95_000,
         wages_sp=55_000, spouse=True, withholding=16_000),
    Case("2026_mfs_wages", "Married filing separately, wages only", MFS,
         "filing status MFS", wages_tp=85_025, spouse=True, withholding=9_000),
    Case("2026_hoh_one_child", "Head of household, one child", HOH,
         "filing status HoH; child tax credit fully nonrefundable",
         wages_tp=70_025, kids=("2016-05-10",), withholding=3_000),
    Case("2026_qss_one_child", "Qualifying surviving spouse, one child", QSS,
         "filing status QSS (joint brackets and standard deduction)",
         wages_tp=120_025, kids=("2014-03-01",), withholding=8_000),
    Case("2026_pref_zero_band", "Capital gains inside the 0% band", S,
         "preferential stacking: all qualified dividends and LTCG at 0%",
         wages_tp=40_025, ord_div=3_000, qual_div=3_000, lt=5_000),
    Case("2026_pref_straddle_0_15", "Capital gains straddling 0% and 15%", S,
         "preferential stacking: gain straddles the 0%/15% breakpoint",
         wages_tp=60_025, lt=10_000),
    Case("2026_pref_line25_smaller", "Worksheet line 25: tax on all income is smaller", S,
         "QDCGT worksheet line 25 — the gain sits above the $49,450 0% breakpoint "
         "but inside the 12% bracket, so taxing everything as ordinary income "
         "(line 24) is smaller than the worksheet (line 23)",
         wages_tp=65_625, lt=600,
         notes="Regression fixture: ouch used line 23 without comparing it to "
               "line 24."),
    Case("2026_pref_15_20_niit", "Capital gains across 15%/20%, with NIIT", J,
         "preferential stacking 15%/20%; NIIT on all investment income; "
         "Additional Medicare", wages_tp=400_000, wages_sp=160_000, spouse=True,
         ord_div=20_000, qual_div=20_000, lt=80_000, withholding=150_000),
    Case("2026_niit_partial", "NIIT limited by MAGI over the threshold", S,
         "NIIT where MAGI over $200,000 is less than investment income",
         wages_tp=190_000, interest=5_000, ord_div=10_000, qual_div=8_000,
         lt=15_000, withholding=40_000),
    Case("2026_se_under_wage_base", "W-2 plus Schedule C, under the wage base", S,
         "SE tax with full Social Security part; QBI below the threshold",
         wages_tp=90_000, sched_c=40_000, withholding=15_000),
    Case("2026_se_straddle_wage_base", "W-2 plus Schedule C, straddling the wage base", S,
         "SE Social Security part limited by the W-2 wages; Additional Medicare on SE income",
         wages_tp=160_000, sched_c=50_000, withholding=35_000),
    Case("2026_se_over_wage_base_qbi_phasein", "W-2 over the wage base; QBI in the phase-in", S,
         "SE tax Medicare only; Additional Medicare Part II with a zero "
         "threshold; QBI inside the phase-in range with no W-2 wages paid",
         wages_tp=200_000, sched_c=30_000, withholding=48_000),
    Case("2026_se_spouse_owner", "Spouse-owned Schedule C", J,
         "SE wage base coordinated with the owning spouse's own W-2",
         wages_tp=180_000, wages_sp=20_000, spouse=True, sched_c=60_000,
         c_owner="spouse", withholding=40_000),
    Case("2026_addl_medicare_two_earners", "Additional Medicare: joint over $250,000", J,
         "two earners each under $200,000, joint wages over $250,000",
         wages_tp=150_000, wages_sp=140_000, spouse=True, withholding=45_000),
    Case("2026_addl_medicare_one_earner", "Additional Medicare: single over $200,000", S,
         "one earner over the $200,000 threshold", wages_tp=260_000,
         withholding=60_000),
    Case("2026_itemized_crossover", "Itemized just beats standard + line 12f", S,
         "itemized vs standard crossover with the 2026 0.5% charitable floor "
         "and line 12f", wages_tp=90_000, salt_income=5_000, salt_property=2_000,
         mortgage=9_525, charity_cash=1_500, withholding=9_000),
    Case("2026_salt_cap_binding", "SALT cap binding", J,
         "SALT limited to $40,400 below the $505,000 threshold",
         wages_tp=180_000, wages_sp=120_000, spouse=True, salt_income=30_000,
         salt_property=15_000, mortgage=20_000, charity_cash=5_000,
         withholding=42_000),
    Case("2026_salt_phasedown", "SALT cap in the phase-down band", S,
         "SALT cap reduced by 30% of MAGI over $505,000",
         wages_tp=550_000, salt_income=35_000, salt_property=10_000,
         mortgage=25_000, charity_cash=10_000, withholding=140_000),
    Case("2026_salt_floor", "SALT cap at its $10,000 floor", J,
         "SALT phase-down reaching the floor", wages_tp=400_000,
         wages_sp=300_000, spouse=True, salt_income=40_000,
         salt_property=10_000, mortgage=30_000, charity_cash=20_000,
         withholding=165_000),
    Case("2026_senior_full", "Enhanced deduction for seniors, full $6,000", S,
         "Schedule 1-A Part V below the threshold; additional standard "
         "deduction for age", tp_birth="1955-06-15", pension=30_025,
         ira=20_000, withholding=3_000),
    Case("2026_senior_phaseout_mfj_mtc", "Seniors in the phase-out; AMT credit", J,
         "Schedule 1-A Part V phase-out for two seniors; Form 6251 adds the "
         "senior deduction back (line 1a), which sets the minimum tax credit",
         tp_birth="1958-04-01", sp_birth="1960-09-30", spouse=True,
         wages_tp=120_000, pension=80_000, mtc_carry=12_000, withholding=15_000,
         notes="Regression fixture: ouch left the senior deduction out of AMTI, "
               "understating TMT and overstating the minimum tax credit."),
    Case("2026_ctc_refundable_eic_plateau", "CTC refundable portion; EIC plateau", J,
         "additional child tax credit; EIC at the plateau (3 children)",
         wages_tp=18_000, wages_sp=12_000, spouse=True,
         kids=("2014-07-01", "2017-02-14", "2020-11-30"), withholding=500),
    Case("2026_eic_phaseout_hoh", "EIC in the phase-out", HOH,
         "EIC phase-out (1 child); CTC limited by tax with the rest refundable",
         wages_tp=40_025, kids=("2015-08-01",), withholding=1_000),
    Case("2026_dependent_care_mfj", "Child and dependent care credit, 2026 schedule", J,
         "Form 2441 2026 second-tier phase-down; CTC for two children",
         wages_tp=120_000, wages_sp=40_000, spouse=True,
         kids=("2022-02-01", "2019-06-01"), care=8_000, withholding=10_000),
    Case("2026_amt_capital_gains", "AMT triggered by large capital gains", S,
         "AMT with the exemption phased out at 50%; Form 6251 Part III "
         "breakpoints measured from regular-tax ordinary income",
         wages_tp=150_000, lt=450_000, withholding=110_000,
         notes="Regression fixture: ouch floored the Part III 0% and 15% "
               "bands at the AMT ordinary base (line 17) instead of the "
               "regular-tax ordinary income (lines 20 and 27)."),
    Case("2026_amt_credit_carryforward", "Minimum tax credit with a child tax credit", J,
         "AMT credit carryforward; Form 8801 line 22 nets the child tax credit",
         wages_tp=300_000, spouse=True, kids=("2012-01-15",),
         mtc_carry=20_000, withholding=45_000,
         notes="Regression fixture: ouch compared regular tax before credits "
               "with TMT."),
    Case("2026_capital_loss_carryforward", "Capital loss with carryforward", S,
         "Schedule D netting, $3,000 loss limit, carryover", wages_tp=80_075,
         st=2_000, lt=-9_000, cap_carry=4_000, withholding=8_000),
    Case("2026_schedule_c_loss", "Schedule C loss", S,
         "business loss offsets wages; no SE tax; no QBI deduction",
         wages_tp=70_025, sched_c=-15_000, withholding=4_000),
    Case("2026_tips_overtime_car_loan", "Tips, overtime and car-loan interest", S,
         "Schedule 1-A Parts II–IV, car-loan interest in its phase-out",
         wages_tp=105_025, tips=6_000, overtime=4_000, car_interest=3_000,
         withholding=9_000),
]

STATE_NOTE = ("State figures: {src}. ouch's 2026 {code} file carries these "
              "figures; the derivation types them from the source, not the file.")
CASES += [
    Case("2026_ca_mfj_two_children", "California: joint return, two children", J,
         "CA progressive brackets (Schedule Y), standard deduction, personal and "
         "dependent exemption credits", wages_tp=150_000, wages_sp=100_000,
         spouse=True, kids=("2015-04-01", "2018-09-09"), state="CA",
         withholding=40_000,
         notes=STATE_NOTE.format(src="FTB 2026 Form 540-ES Instructions (2026 "
             "estimated tax worksheet, which uses the 2025 tax table and exemption "
             "credits) and the FTB 2025 Personal Income Tax Booklet", code="CA")),
    Case("2026_ca_single_exemption_phaseout", "California: exemption credit phase-out", S,
         "CA exemption credit AGI limitation ($6 per $2,500 over $252,203)",
         wages_tp=300_000, state="CA", withholding=70_000,
         notes=STATE_NOTE.format(src="FTB 2026 Form 540-ES Instructions and FTB 2025 "
             "Booklet (line 32 AGI Limitation Worksheet)", code="CA")),
    Case("2026_ny_nyc_single", "New York State and New York City resident", S,
         "NY progressive (2026 rates), NYC tax on NY taxable income, NYC school "
         "tax credits", wages_tp=100_025, state="NY", locality="NYC",
         withholding=14_000,
         notes=STATE_NOTE.format(src="NY DTF Instructions for Form IT-2105 (2026)",
                                 code="NY and NYC")),
    Case("2026_co_overtime_addback", "Colorado: overtime addback", S,
         "CO flat rate on federal taxable income; 2026 overtime deduction addback",
         wages_tp=120_025, overtime=6_000, state="CO", withholding=17_000,
         notes=STATE_NOTE.format(src="CO DOR Individual Income Tax Guide (rev. "
             "January 2026), Part 3; the 4.4% rate is 2025's, carried to 2026",
             code="CO")),
    Case("2026_co_high_income_deduction_addback", "Colorado: deduction addback over $300,000 AGI", S,
         "CO addback of the federal standard deduction above $1,000 (2026) for "
         "AGI over $300,000", wages_tp=400_000, state="CO", withholding=120_000,
         notes=STATE_NOTE.format(src="CO DOR Individual Income Tax Guide (rev. "
             "January 2026), Part 3", code="CO")),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tables", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--only")
    a = ap.parse_args()
    raw = json.loads(Path(a.tables).read_text())
    tables = Tables(tax=raw["tax"], eic=raw["eic"])
    for c in CASES:
        if a.only and a.only != c.name:
            continue
        expected, lines = derive(c, tables)
        d = Path(a.out) / c.name
        d.mkdir(parents=True, exist_ok=True)
        (d / "profile.toml").write_text(toml_profile(c))
        (d / "expected.json").write_text(json.dumps(expected, indent=2) + "\n")
        (d / "SOURCE.md").write_text(source_md(c, lines))
        print(c.name, expected["federal_total_tax"])


if __name__ == "__main__":
    main()
