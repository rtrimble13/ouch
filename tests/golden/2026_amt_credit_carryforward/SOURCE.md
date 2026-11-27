# Minimum tax credit with a child tax credit

**Covers:** AMT credit carryforward; Form 8801 line 22 nets the child tax credit

## Derivation basis

Worked line by line through the 2026 forms with figures from Rev. Proc.
2025-32 §4 and the 2026 IRS forms and draft instructions cited in
`tests/golden_derive/derive.py`, which does not import ouch. Tax on
taxable income below $100,000 is read from the 2026 Tax Table and the
earned income credit from the 2026 EIC Table (draft 2026 Instructions
for Form 1040), not computed by formula; the harness compares money
fields to the dollar (spec §19). **Not** produced by running `ouch`
(spec §16.2).

Regression fixture: ouch compared regular tax before credits with TMT.

## Computation

### Income (Form 1040 lines 1–11)
- Line 1a wages: 300,000.00
- **Line 9 total income: 300,000.00**
- **Line 11 AGI: 300,000.00**

### Deductions (lines 12–14)
- Standard deduction: 32,200
- **Line 12e: 32,200.00 (standard)**
- **Line 15 taxable income: 267,800.00**

### Tax (line 16)
  - tax on 267,800.00 (Tax Computation Worksheet, married_filing_jointly) = 49,468.00
- **Line 16: 49,468.00**

### Form 6251 (AMT)
- line 1b = taxable income 267,800.00 = 267,800.00
- line 2a (line 12e standard deduction): 32,200.00
- line 4 AMTI: 300,000.00
- line 5 exemption: 140,200.00
- line 6: 159,800.00
- line 7: 26% → 41,548.00
- line 9 TMT 41,548.00; line 10 regular tax 49,468.00
- **line 11 AMT: 0.00**

### Credits
- Schedule 8812: line 8 = 1 × 2,200 = 2,200.00; line 11 = 0.00; line 12 = 2,200.00; line 13 (Credit Limit Worksheet A) = 49,468.00; **line 14 = 2,200.00**
- Form 8801: line 21 carryforward 20,000.00; line 22 = line 16 49,468.00 − credits 2,200.00 = 47,268.00; line 23 TMT 41,548.00; line 24 5,720.00; **line 25 credit 5,720.00**; carryforward to 2027 14,280.00

### Other taxes (Schedule 2)
- Form 8959: Part I 0.9% × (300,000.00 − 250,000.00) = 450.00 → **450.00**

### Totals
- Line 24 total tax = 49,468.00 + 0.00 − 7,920.00 + 450.00 = 41,998.00
- ouch `federal_total_tax` (line 24 less refundable credits): **41,998.00**
- Payments (withholding): 45,000.00 → balance -3,002.00
