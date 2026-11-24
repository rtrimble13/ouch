"""Built-in scenario templates (spec §12.5). `ouch scenario new NAME
--template TEMPLATE` scaffolds one; the user edits the numbers."""

TEMPLATES: dict[str, str] = {
    "roth-conversion": '''name        = "{name}"
base        = "{base}"
description = "Convert from traditional IRA before year end"
tags        = ["retirement"]

[patch]
"income.retirement.roth_conversion" = 75_000

[assert]
# fail the run if the conversion pushes the marginal rate too high
"result.marginal_rate_federal" = {{lt = 0.35}}
''',
    "bonus-deferral": '''name        = "{name}"
base        = "{base}"
description = "Defer a year-end bonus into next year"
tags        = ["timing"]

[patch]
"income.wages.taxpayer_w2" = "-25000"
''',
    "hsa-max": '''name        = "{name}"
base        = "{base}"
description = "Max the HSA (family limit — verify the year's figure)"
tags        = ["deduction"]

[patch]
"adjustments.hsa" = 8_300
''',
    "bunch-charitable": '''name        = "{name}"
base        = "{base}"
description = "Bunch two years of charitable gifts into this year"
tags        = ["itemized"]

[patch]
"deductions.itemized.charitable_cash" = "+100%"
''',
    "relocate-state": '''name        = "{name}"
base        = "{base}"
description = "Move to a no-income-tax state (income tax only — property, sales, insurance and cost of living are outside ouch's scope)"
tags        = ["relocation"]

[patch]
"taxpayer.state"    = "TX"
"taxpayer.locality" = ""
''',
    "solo401k": '''name        = "{name}"
base        = "{base}"
description = "Solo 401(k) employee deferral against Schedule C income"
tags        = ["retirement", "self-employment"]

[patch]
"adjustments.sep_solo401k" = 10_000
''',
}
