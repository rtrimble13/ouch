# Derivation basis

Hand computation from the 2025 federal parameters in
`ouch/taxdata/data/federal/2025.yaml` (single filer), performed on paper
independently of the engine. **Not** produced by running `ouch` (spec §16.2).

## Computation

Income: wages 142,000 + interest 850 + ordinary dividends 2,100
+ LTCG 3,400 = **148,350** total income = AGI (no adjustments).

Standard deduction (single): 15,000 → taxable income **133,350**.

Preferential income = qualified dividends 1,950 + LTCG 3,400 = 5,350.
Ordinary taxable = 133,350 − 5,350 = 128,000.

Ordinary brackets (single):

| Band | Amount | Tax |
|---|---|---|
| 10% × 11,925 | 11,925 | 1,192.50 |
| 12% × (48,475 − 11,925) | 36,550 | 4,386.00 |
| 22% × (103,350 − 48,475) | 54,875 | 12,072.50 |
| 24% × (128,000 − 103,350) | 24,650 | 5,916.00 |
| **Total ordinary** | | **23,567.00** |

Preferential stacking: floor = 128,000, above the 0% ceiling (48,350),
below the 20% threshold (533,400) → all 5,350 at 15% = **802.50**.

No SE income, AGI below the NIIT/Additional-Medicare thresholds, no
dependents, TX has no income tax.

Federal total = 23,567.00 + 802.50 = **24,369.50**.
Payments = 21,400 withheld → balance due **2,969.50**.

## Cross-check

Bracket arithmetic re-verified with a calculator; the preferential floor
logic follows the Qualified Dividends and Capital Gain Tax Worksheet
structure (2024 Form 1040 instructions), with 2025 thresholds from
Rev. Proc. 2024-40.
