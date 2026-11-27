# Seniors in the phase-out; AMT credit

**Covers:** Schedule 1-A Part V phase-out for two seniors; Form 6251 adds the senior deduction back (line 1a), which sets the minimum tax credit

## Derivation basis

Worked line by line through the 2026 forms with figures from Rev. Proc.
2025-32 §4 and the 2026 IRS forms and draft instructions cited in
`tests/golden_derive/derive.py`, which does not import ouch. Tax on
taxable income below $100,000 is read from the 2026 Tax Table and the
earned income credit from the 2026 EIC Table (draft 2026 Instructions
for Form 1040), not computed by formula; the harness compares money
fields to the dollar (spec §19). **Not** produced by running `ouch`
(spec §16.2).

Regression fixture: ouch left the senior deduction out of AMTI, understating TMT and overstating the minimum tax credit.

## Computation

### Income (Form 1040 lines 1–11)
- Line 1a wages: 120,000.00
- Line 5b pensions: 80,000.00
- **Line 9 total income: 200,000.00**
- **Line 11 AGI: 200,000.00**

### Deductions (lines 12–14)
- Standard deduction: 32,200 + 2 × 1,650 (65 or older) = 35,500.00
- **Line 12e: 35,500.00 (standard)**
- Schedule 1-A Part V: line 39 = 200,000.00 − 150,000.00 = 50,000.00; line 41 = 6,000 − 6% × 50,000.00 = 3,000.00; × 2 = **6,000.00** (line 13a)
- **Line 15 taxable income: 158,500.00**

### Tax (line 16)
  - tax on 158,500.00 (Tax Computation Worksheet, married_filing_jointly) = 24,294.00
- **Line 16: 24,294.00**

### Form 6251 (AMT)
- line 1b = taxable income 158,500.00 + Schedule 1-A line 43 senior deduction 6,000.00 = 164,500.00
- line 2a (line 12e standard deduction): 35,500.00
- line 4 AMTI: 200,000.00
- line 5 exemption: 140,200.00
- line 6: 59,800.00
- line 7: 26% → 15,548.00
- line 9 TMT 15,548.00; line 10 regular tax 24,294.00
- **line 11 AMT: 0.00**

### Credits
- Form 8801: line 21 carryforward 12,000.00; line 22 = line 16 24,294.00 − credits 0.00 = 24,294.00; line 23 TMT 15,548.00; line 24 8,746.00; **line 25 credit 8,746.00**; carryforward to 2027 3,254.00

### Other taxes (Schedule 2)
- none

### Totals
- Line 24 total tax = 24,294.00 + 0.00 − 8,746.00 + 0.00 = 15,548.00
- ouch `federal_total_tax` (line 24 less refundable credits): **15,548.00**
- Payments (withholding): 15,000.00 → balance 548.00
