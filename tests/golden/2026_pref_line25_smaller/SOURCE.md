# Worksheet line 25: tax on all income is smaller

**Covers:** QDCGT worksheet line 25 — the gain sits above the $49,450 0% breakpoint but inside the 12% bracket, so taxing everything as ordinary income (line 24) is smaller than the worksheet (line 23)

## Derivation basis

Worked line by line through the 2026 forms with figures from Rev. Proc.
2025-32 §4 and the 2026 IRS forms and draft instructions cited in
`tests/golden_derive/derive.py`, which does not import ouch. Tax on
taxable income below $100,000 is read from the 2026 Tax Table and the
earned income credit from the 2026 EIC Table (draft 2026 Instructions
for Form 1040), not computed by formula; the harness compares money
fields to the dollar (spec §19). **Not** produced by running `ouch`
(spec §16.2).

Regression fixture: ouch used line 23 without comparing it to line 24.

## Computation

### Income (Form 1040 lines 1–11)
- Line 1a wages: 65,625.00
- Schedule D: line 7 short-term 0.00; line 15 long-term 600.00
  - line 16 = 600.00
- Line 7a capital gain or (loss): 600.00
- **Line 9 total income: 66,225.00**
- **Line 11 AGI: 66,225.00**

### Deductions (lines 12–14)
- Standard deduction: 16,100
- **Line 12e: 16,100.00 (standard)**
- **Line 15 taxable income: 50,125.00**

### Tax (line 16)
Qualified Dividends and Capital Gain Tax Worksheet (I1040):
- line 1 50,125.00; line 4 600.00; line 5 49,525.00
- line 6 49,450.00; line 9 taxed at 0%: 0.00
- line 17 at 15%: 600.00 → line 18 90.00
- line 20 at 20%: 0.00 → line 21 0.00
  - tax on 49,525.00: 2026 Tax Table row 49,500–49,550, single column = 5,695
- line 22 (tax on line 5): 5,695.00
  - tax on 50,125.00: 2026 Tax Table row 50,100–50,150, single column = 5,767
- line 23 = 5,785.00; line 24 (tax on line 1) = 5,767.00
- **line 25 = smaller of 23 and 24 = 5,767.00**

### Form 6251 (AMT)
- line 1b = taxable income 50,125.00 = 50,125.00
- line 2a (line 12e standard deduction): 16,100.00
- line 4 AMTI: 66,225.00
- line 5 exemption: 90,100.00
- line 6: 0.00
- line 7: 26% → 0.00
- line 9 TMT 0.00; line 10 regular tax 5,767.00
- **line 11 AMT: 0.00**

### Credits
- none

### Other taxes (Schedule 2)
- none

### Totals
- Line 24 total tax = 5,767.00 + 0.00 − 0.00 + 0.00 = 5,767.00
- ouch `federal_total_tax` (line 24 less refundable credits): **5,767.00**
- Payments (withholding): 0.00 → balance 5,767.00
