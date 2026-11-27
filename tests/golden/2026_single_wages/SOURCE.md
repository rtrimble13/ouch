# Single, wages only

**Covers:** filing status single; Tax Table

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
- **Line 9 total income: 60,025.00**
- **Line 11 AGI: 60,025.00**

### Deductions (lines 12–14)
- Standard deduction: 16,100
- **Line 12e: 16,100.00 (standard)**
- **Line 15 taxable income: 43,925.00**

### Tax (line 16)
  - tax on 43,925.00: 2026 Tax Table row 43,900–43,950, single column = 5,023
- **Line 16: 5,023.00**

### Form 6251 (AMT)
- line 1b = taxable income 43,925.00 = 43,925.00
- line 2a (line 12e standard deduction): 16,100.00
- line 4 AMTI: 60,025.00
- line 5 exemption: 90,100.00
- line 6: 0.00
- line 7: 26% → 0.00
- line 9 TMT 0.00; line 10 regular tax 5,023.00
- **line 11 AMT: 0.00**

### Credits
- none

### Other taxes (Schedule 2)
- none

### Totals
- Line 24 total tax = 5,023.00 + 0.00 − 0.00 + 0.00 = 5,023.00
- ouch `federal_total_tax` (line 24 less refundable credits): **5,023.00**
- Payments (withholding): 5,500.00 → balance -477.00
