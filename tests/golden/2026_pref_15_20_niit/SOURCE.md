# Capital gains across 15%/20%, with NIIT

**Covers:** preferential stacking 15%/20%; NIIT on all investment income; Additional Medicare

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
- Line 1a wages: 560,000.00 (taxpayer 400,000.00, spouse 160,000.00)
- Line 3a qualified dividends 20,000.00; line 3b ordinary dividends 20,000.00
- Schedule D: line 7 short-term 0.00; line 15 long-term 80,000.00
  - line 16 = 80,000.00
- Line 7a capital gain or (loss): 80,000.00
- **Line 9 total income: 660,000.00**
- **Line 11 AGI: 660,000.00**

### Deductions (lines 12–14)
- Standard deduction: 32,200
- **Line 12e: 32,200.00 (standard)**
- **Line 15 taxable income: 627,800.00**

### Tax (line 16)
Qualified Dividends and Capital Gain Tax Worksheet (I1040):
- line 1 627,800.00; line 4 100,000.00; line 5 527,800.00
- line 6 98,900.00; line 9 taxed at 0%: 0.00
- line 17 at 15%: 85,900.00 → line 18 12,885.00
- line 20 at 20%: 14,100.00 → line 21 2,820.00
  - tax on 527,800.00 (Tax Computation Worksheet, married_filing_jointly) = 122,268.50
- line 22 (tax on line 5): 122,268.50
  - tax on 627,800.00 (Tax Computation Worksheet, married_filing_jointly) = 157,268.50
- line 23 = 137,973.50; line 24 (tax on line 1) = 157,268.50
- **line 25 = smaller of 23 and 24 = 137,973.50**

### Form 6251 (AMT)
- line 1b = taxable income 627,800.00 = 627,800.00
- line 2a (line 12e standard deduction): 32,200.00
- line 4 AMTI: 660,000.00
- line 5 exemption: 140,200.00
- line 6: 519,800.00
- Part III: line 17 ordinary AMT base 419,800.00 → line 18 112,654.00
  - line 20 = QDCGT worksheet line 5 (regular tax) 527,800.00; line 21 = 0.00; line 23 at 0%: 0.00
  - line 29 = 613,700.00 − (line 21 + line 27 = 527,800.00) = 85,900.00; line 30 at 15%: 85,900.00 → 12,885.00
  - line 33 at 20%: 14,100.00 → 2,820.00
  - line 38 = 128,359.00; line 39 (all at AMT rates) = 140,654.00; line 40 = 128,359.00
- line 9 TMT 128,359.00; line 10 regular tax 137,973.50
- **line 11 AMT: 0.00**

### Credits
- none

### Other taxes (Schedule 2)
- Form 8959: Part I 0.9% × (560,000.00 − 250,000.00) = 2,790.00 → **2,790.00**
- Form 8960: NII 100,000.00; MAGI over 250,000.00 = 410,000.00; 3.8% × smaller = **3,800.00**

### Totals
- Line 24 total tax = 137,973.50 + 0.00 − 0.00 + 6,590.00 = 144,563.50
- ouch `federal_total_tax` (line 24 less refundable credits): **144,563.50**
- Payments (withholding): 150,000.00 → balance -5,436.50
