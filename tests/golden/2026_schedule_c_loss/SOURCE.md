# Schedule C loss

**Covers:** business loss offsets wages; no SE tax; no QBI deduction

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
- Line 1a wages: 70,025.00
- Schedule C loss -15,000.00: no SE tax (net earnings below $400)
- Schedule 1 line 3 business income: -15,000.00
- **Line 9 total income: 55,025.00**
- **Line 11 AGI: 55,025.00**

### Deductions (lines 12–14)
- Standard deduction: 16,100
- **Line 12e: 16,100.00 (standard)**
- QBI: a -15,000.00 business loss → deduction 0; the loss carries forward as a qualified business loss
- **Line 15 taxable income: 38,925.00**

### Tax (line 16)
  - tax on 38,925.00: 2026 Tax Table row 38,900–38,950, single column = 4,423
- **Line 16: 4,423.00**

### Form 6251 (AMT)
- line 1b = taxable income 38,925.00 = 38,925.00
- line 2a (line 12e standard deduction): 16,100.00
- line 4 AMTI: 55,025.00
- line 5 exemption: 90,100.00
- line 6: 0.00
- line 7: 26% → 0.00
- line 9 TMT 0.00; line 10 regular tax 4,423.00
- **line 11 AMT: 0.00**

### Credits
- none

### Other taxes (Schedule 2)
- none

### Totals
- Line 24 total tax = 4,423.00 + 0.00 − 0.00 + 0.00 = 4,423.00
- ouch `federal_total_tax` (line 24 less refundable credits): **4,423.00**
- Payments (withholding): 4,000.00 → balance 423.00
