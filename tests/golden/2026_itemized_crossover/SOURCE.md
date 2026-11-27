# Itemized just beats standard + line 12f

**Covers:** itemized vs standard crossover with the 2026 0.5% charitable floor and line 12f

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
- Line 1a wages: 90,000.00
- **Line 9 total income: 90,000.00**
- **Line 11 AGI: 90,000.00**

### Deductions (lines 12–14)
- Standard deduction: 16,100
- Schedule A line 5d SALT paid 7,000.00 → line 5e 7,000.00
- Schedule A line 8a mortgage interest 9,525.00
- Charity: cash 1,500.00 − 0.5% × AGI (450.00) = 1,050.00
- Schedule A line 17 total itemized: 17,575.00
- Itemized 17,575.00 beats standard 16,100.00 + line 12f → itemize
- **Line 12e: 17,575.00 (itemized)**
- **Line 15 taxable income: 72,425.00**

### Tax (line 16)
  - tax on 72,425.00: 2026 Tax Table row 72,400–72,450, single column = 10,646
- **Line 16: 10,646.00**

### Form 6251 (AMT)
- line 1b = taxable income 72,425.00 = 72,425.00
- line 2a (Schedule A line 7 taxes): 7,000.00
- line 4 AMTI: 79,425.00
- line 5 exemption: 90,100.00
- line 6: 0.00
- line 7: 26% → 0.00
- line 9 TMT 0.00; line 10 regular tax 10,646.00
- **line 11 AMT: 0.00**

### Credits
- none

### Other taxes (Schedule 2)
- none

### Totals
- Line 24 total tax = 10,646.00 + 0.00 − 0.00 + 0.00 = 10,646.00
- ouch `federal_total_tax` (line 24 less refundable credits): **10,646.00**
- Payments (withholding): 9,000.00 → balance 1,646.00
