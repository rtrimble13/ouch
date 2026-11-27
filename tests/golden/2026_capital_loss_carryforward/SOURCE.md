# Capital loss with carryforward

**Covers:** Schedule D netting, $3,000 loss limit, carryover

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
- Line 1a wages: 80,075.00
- Schedule D: line 7 short-term 2,000.00; line 15 long-term -9,000.00 − carryover 4,000.00 = -13,000.00
  - line 16 = -11,000.00
  - line 21 loss allowed: -3,000.00 (limit $3,000); carryover to 2027 = 8,000.00
- Line 7a capital gain or (loss): -3,000.00
- **Line 9 total income: 77,075.00**
- **Line 11 AGI: 77,075.00**

### Deductions (lines 12–14)
- Standard deduction: 16,100
- **Line 12e: 16,100.00 (standard)**
- **Line 15 taxable income: 60,975.00**

### Tax (line 16)
  - tax on 60,975.00: 2026 Tax Table row 60,950–61,000, single column = 8,127
- **Line 16: 8,127.00**

### Form 6251 (AMT)
- line 1b = taxable income 60,975.00 = 60,975.00
- line 2a (line 12e standard deduction): 16,100.00
- line 4 AMTI: 77,075.00
- line 5 exemption: 90,100.00
- line 6: 0.00
- line 7: 26% → 0.00
- line 9 TMT 0.00; line 10 regular tax 8,127.00
- **line 11 AMT: 0.00**

### Credits
- none

### Other taxes (Schedule 2)
- none

### Totals
- Line 24 total tax = 8,127.00 + 0.00 − 0.00 + 0.00 = 8,127.00
- ouch `federal_total_tax` (line 24 less refundable credits): **8,127.00**
- Payments (withholding): 8,000.00 → balance 127.00
