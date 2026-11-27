# NIIT limited by MAGI over the threshold

**Covers:** NIIT where MAGI over $200,000 is less than investment income

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
- Line 1a wages: 190,000.00
- Line 2b taxable interest: 5,000.00
- Line 3a qualified dividends 8,000.00; line 3b ordinary dividends 10,000.00
- Schedule D: line 7 short-term 0.00; line 15 long-term 15,000.00
  - line 16 = 15,000.00
- Line 7a capital gain or (loss): 15,000.00
- **Line 9 total income: 220,000.00**
- **Line 11 AGI: 220,000.00**

### Deductions (lines 12–14)
- Standard deduction: 16,100
- **Line 12e: 16,100.00 (standard)**
- **Line 15 taxable income: 203,900.00**

### Tax (line 16)
Qualified Dividends and Capital Gain Tax Worksheet (I1040):
- line 1 203,900.00; line 4 23,000.00; line 5 180,900.00
- line 6 49,450.00; line 9 taxed at 0%: 0.00
- line 17 at 15%: 23,000.00 → line 18 3,450.00
- line 20 at 20%: 0.00 → line 21 0.00
  - tax on 180,900.00 (Tax Computation Worksheet, single) = 36,014.00
- line 22 (tax on line 5): 36,014.00
  - tax on 203,900.00 (Tax Computation Worksheet, single) = 41,704.00
- line 23 = 39,464.00; line 24 (tax on line 1) = 41,704.00
- **line 25 = smaller of 23 and 24 = 39,464.00**

### Form 6251 (AMT)
- line 1b = taxable income 203,900.00 = 203,900.00
- line 2a (line 12e standard deduction): 16,100.00
- line 4 AMTI: 220,000.00
- line 5 exemption: 90,100.00
- line 6: 129,900.00
- Part III: line 17 ordinary AMT base 106,900.00 → line 18 27,794.00
  - line 20 = QDCGT worksheet line 5 (regular tax) 180,900.00; line 21 = 0.00; line 23 at 0%: 0.00
  - line 29 = 545,500.00 − (line 21 + line 27 = 180,900.00) = 364,600.00; line 30 at 15%: 23,000.00 → 3,450.00
  - line 33 at 20%: 0.00 → 0.00
  - line 38 = 31,244.00; line 39 (all at AMT rates) = 33,774.00; line 40 = 31,244.00
- line 9 TMT 31,244.00; line 10 regular tax 39,464.00
- **line 11 AMT: 0.00**

### Credits
- none

### Other taxes (Schedule 2)
- Form 8960: NII 30,000.00; MAGI over 200,000.00 = 20,000.00; 3.8% × smaller = **760.00**

### Totals
- Line 24 total tax = 39,464.00 + 0.00 − 0.00 + 760.00 = 40,224.00
- ouch `federal_total_tax` (line 24 less refundable credits): **40,224.00**
- Payments (withholding): 40,000.00 → balance 224.00
