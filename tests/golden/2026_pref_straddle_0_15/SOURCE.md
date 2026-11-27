# Capital gains straddling 0% and 15%

**Covers:** preferential stacking: gain straddles the 0%/15% breakpoint

## Derivation basis

Worked line by line through the 2026 forms with figures from Rev. Proc.
2025-32 §4 and the 2026 IRS forms and draft instructions cited in
`tests/golden_derive/derive.py`, which does not import ouch. Tax on
taxable income below $100,000 is read from the 2026 Tax Table and the
earned income credit from the 2026 EIC Table (draft 2026 Instructions
for Form 1040), not computed by formula; the harness compares money
fields to the dollar (spec §19). **Not** produced by running `ouch`
(spec §16.2).

## Computation

### Income (Form 1040 lines 1–11)
- Line 1a wages: 60,025.00
- Schedule D: line 7 short-term 0.00; line 15 long-term 10,000.00
  - line 16 = 10,000.00
- Line 7a capital gain or (loss): 10,000.00
- **Line 9 total income: 70,025.00**
- **Line 11 AGI: 70,025.00**

### Deductions (lines 12–14)
- Standard deduction: 16,100
- **Line 12e: 16,100.00 (standard)**
- **Line 15 taxable income: 53,925.00**

### Tax (line 16)
Qualified Dividends and Capital Gain Tax Worksheet (I1040):
- line 1 53,925.00; line 4 10,000.00; line 5 43,925.00
- line 6 49,450.00; line 9 taxed at 0%: 5,525.00
- line 17 at 15%: 4,475.00 → line 18 671.25
- line 20 at 20%: 0.00 → line 21 0.00
  - tax on 43,925.00: 2026 Tax Table row 43,900–43,950, single column = 5,023
- line 22 (tax on line 5): 5,023.00
  - tax on 53,925.00: 2026 Tax Table row 53,900–53,950, single column = 6,576
- line 23 = 5,694.25; line 24 (tax on line 1) = 6,576.00
- **line 25 = smaller of 23 and 24 = 5,694.25**

### Form 6251 (AMT)
- line 1b = taxable income 53,925.00 = 53,925.00
- line 2a (line 12e standard deduction): 16,100.00
- line 4 AMTI: 70,025.00
- line 5 exemption: 90,100.00
- line 6: 0.00
- line 7: 26% → 0.00
- line 9 TMT 0.00; line 10 regular tax 5,694.25
- **line 11 AMT: 0.00**

### Credits
- none

### Other taxes (Schedule 2)
- none

### Totals
- Line 24 total tax = 5,694.25 + 0.00 − 0.00 + 0.00 = 5,694.25
- ouch `federal_total_tax` (line 24 less refundable credits): **5,694.25**
- Payments (withholding): 0.00 → balance 5,694.25
