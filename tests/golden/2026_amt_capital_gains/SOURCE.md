# AMT triggered by large capital gains

**Covers:** AMT with the exemption phased out at 50%; Form 6251 Part III breakpoints measured from regular-tax ordinary income

## Derivation basis

Worked line by line through the 2026 forms with figures from Rev. Proc.
2025-32 §4 and the 2026 IRS forms and draft instructions cited in
`tests/golden_derive/derive.py`, which does not import ouch. Tax on
taxable income below $100,000 is read from the 2026 Tax Table and the
earned income credit from the 2026 EIC Table (draft 2026 Instructions
for Form 1040), not computed by formula; the harness compares money
fields to the dollar (spec §19). **Not** produced by running `ouch`
(spec §16.2).

Regression fixture: ouch floored the Part III 0% and 15% bands at the AMT ordinary base (line 17) instead of the regular-tax ordinary income (lines 20 and 27).

## Computation

### Income (Form 1040 lines 1–11)
- Line 1a wages: 150,000.00
- Schedule D: line 7 short-term 0.00; line 15 long-term 450,000.00
  - line 16 = 450,000.00
- Line 7a capital gain or (loss): 450,000.00
- **Line 9 total income: 600,000.00**
- **Line 11 AGI: 600,000.00**

### Deductions (lines 12–14)
- Standard deduction: 16,100
- **Line 12e: 16,100.00 (standard)**
- **Line 15 taxable income: 583,900.00**

### Tax (line 16)
Qualified Dividends and Capital Gain Tax Worksheet (I1040):
- line 1 583,900.00; line 4 450,000.00; line 5 133,900.00
- line 6 49,450.00; line 9 taxed at 0%: 0.00
- line 17 at 15%: 411,600.00 → line 18 61,740.00
- line 20 at 20%: 38,400.00 → line 21 7,680.00
  - tax on 133,900.00 (Tax Computation Worksheet, single) = 24,734.00
- line 22 (tax on line 5): 24,734.00
  - tax on 583,900.00 (Tax Computation Worksheet, single) = 173,134.25
- line 23 = 94,154.00; line 24 (tax on line 1) = 173,134.25
- **line 25 = smaller of 23 and 24 = 94,154.00**

### Form 6251 (AMT)
- line 1b = taxable income 583,900.00 = 583,900.00
- line 2a (line 12e standard deduction): 16,100.00
- line 4 AMTI: 600,000.00
- line 5 exemption: 40,100.00 (= 90,100 − 50% × 100,000.00)
- line 6: 559,900.00
- Part III: line 17 ordinary AMT base 109,900.00 → line 18 28,574.00
  - line 20 = QDCGT worksheet line 5 (regular tax) 133,900.00; line 21 = 0.00; line 23 at 0%: 0.00
  - line 29 = 545,500.00 − (line 21 + line 27 = 133,900.00) = 411,600.00; line 30 at 15%: 411,600.00 → 61,740.00
  - line 33 at 20%: 38,400.00 → 7,680.00
  - line 38 = 97,994.00; line 39 (all at AMT rates) = 151,882.00; line 40 = 97,994.00
- line 9 TMT 97,994.00; line 10 regular tax 94,154.00
- **line 11 AMT: 3,840.00**

### Credits
- none

### Other taxes (Schedule 2)
- Form 8960: NII 450,000.00; MAGI over 200,000.00 = 400,000.00; 3.8% × smaller = **15,200.00**

### Totals
- Line 24 total tax = 94,154.00 + 3,840.00 − 0.00 + 15,200.00 = 113,194.00
- ouch `federal_total_tax` (line 24 less refundable credits): **113,194.00**
- Payments (withholding): 110,000.00 → balance 3,194.00
