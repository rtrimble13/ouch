# SALT cap in the phase-down band

**Covers:** SALT cap reduced by 30% of MAGI over $505,000

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
- Line 1a wages: 550,000.00
- **Line 9 total income: 550,000.00**
- **Line 11 AGI: 550,000.00**

### Deductions (lines 12–14)
- Standard deduction: 16,100
- SALT cap: AGI 550,000.00 over $505,000 → max(10,000, 40,400 − 30% × 45,000.00) = 26,900.00
- Schedule A line 5d SALT paid 45,000.00 → line 5e 26,900.00
- Schedule A line 8a mortgage interest 25,000.00
- Charity: cash 10,000.00 − 0.5% × AGI (2,750.00) = 7,250.00
- Schedule A line 17 total itemized: 59,150.00
- Itemized 59,150.00 beats standard 16,100.00 + line 12f → itemize
- **Line 12e: 59,150.00 (itemized)**
- **Line 15 taxable income: 490,850.00**

### Tax (line 16)
  - tax on 490,850.00 (Tax Computation Worksheet, single) = 140,566.75
- **Line 16: 140,566.75**

### Form 6251 (AMT)
- line 1b = taxable income 490,850.00 = 490,850.00
- line 2a (Schedule A line 7 taxes): 26,900.00
- line 4 AMTI: 517,750.00
- line 5 exemption: 81,225.00 (= 90,100 − 50% × 17,750.00)
- line 6: 436,525.00
- line 7: 28% − 4,890.00 → 117,337.00
- line 9 TMT 117,337.00; line 10 regular tax 140,566.75
- **line 11 AMT: 0.00**

### Credits
- none

### Other taxes (Schedule 2)
- Form 8959: Part I 0.9% × (550,000.00 − 200,000.00) = 3,150.00 → **3,150.00**

### Totals
- Line 24 total tax = 140,566.75 + 0.00 − 0.00 + 3,150.00 = 143,716.75
- ouch `federal_total_tax` (line 24 less refundable credits): **143,716.75**
- Payments (withholding): 140,000.00 → balance 3,716.75
