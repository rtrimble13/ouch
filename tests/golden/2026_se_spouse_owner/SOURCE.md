# Spouse-owned Schedule C

**Covers:** SE wage base coordinated with the owning spouse's own W-2

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
- Line 1a wages: 200,000.00 (taxpayer 180,000.00, spouse 20,000.00)
- Schedule SE (spouse): net earnings 92.35% × 60,000.00 = 55,410.00
  - Social Security part: room under the $184,500 wage base = 184,500 − spouse's W-2 20,000.00 = 164,500.00; 12.4% × 55,410.00 = 6,870.84
  - Medicare part: 2.9% × 55,410.00 = 1,606.89
  - SE tax 8,477.73; deductible half (Schedule 1 line 15) 4,238.87
- Schedule 1 line 3 business income: 60,000.00
- **Line 9 total income: 260,000.00**
- Line 10 adjustments: 4,238.87 (half of SE tax)
- **Line 11 AGI: 255,761.14**

### Deductions (lines 12–14)
- Standard deduction: 32,200
- **Line 12e: 32,200.00 (standard)**
- QBI: 60,000.00 − deductible SE tax 4,238.87 = 55,761.14; 20% = 11,152.23
  - taxable income before QBI = 255,761.14 − 32,200.00 = 223,561.14
  - income limit 20% × (223,561.14 − net capital gain 0.00) = 44,712.23 → **QBI deduction 11,152.23** (line 13b)
- **Line 15 taxable income: 212,408.91**

### Tax (line 16)
  - tax on 212,408.91 (Tax Computation Worksheet, married_filing_jointly) = 36,174.14
- **Line 16: 36,174.14**

### Form 6251 (AMT)
- line 1b = taxable income 212,408.91 = 212,408.91
- line 2a (line 12e standard deduction): 32,200.00
- line 4 AMTI: 244,608.91
- line 5 exemption: 140,200.00
- line 6: 104,408.91
- line 7: 26% → 27,146.32
- line 9 TMT 27,146.32; line 10 regular tax 36,174.14
- **line 11 AMT: 0.00**

### Credits
- none

### Other taxes (Schedule 2)
- Form 8959: Part I 0.9% × (200,000.00 − 250,000.00) = 0.00; Part II 0.9% × (55,410.00 − max(0, 250,000.00 − 200,000.00)) = 48.69 → **48.69**
- Schedule SE tax: 8,477.73

### Totals
- Line 24 total tax = 36,174.14 + 0.00 − 0.00 + 8,526.42 = 44,700.56
- ouch `federal_total_tax` (line 24 less refundable credits): **44,700.56**
- Payments (withholding): 40,000.00 → balance 4,700.56
