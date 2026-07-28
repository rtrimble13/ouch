# `ouch` vignettes

Ten tutorials that teach the whole tool through realistic situations. Each one
introduces a capability by way of a person with a problem, shows the real
commands and real output, and explains what the numbers mean.

Work through them in order and you will have used every command `ouch` has.

> All people, incomes, and portfolios below are invented. All command output is
> real — produced by running the commands shown against the profiles shown,
> using the tax data that ships with `ouch`. **That data is projected and
> unverified**, so treat every figure as illustrative of the *tool*, not
> authoritative about the *law*. (Vignette 9 is the one exception: the AI
> model's *answers* there are written for the tutorial, since running a live
> session would transmit data. It says so at the top.)
>
> Where a command misbehaves, the vignettes say so and give the workaround. The
> full list is in the manual's
> [known defects](../MANUAL.md#known-defects) table.

---

## The path

| # | Vignette | You will learn |
|---|---|---|
| 1 | [What do I actually pay?](01-first-estimate.md) | `init`, `estimate`, `explain`, marginal vs effective rate, preferential stacking |
| 2 | [The April surprise, fixed in July](02-the-april-surprise.md) | `withhold check`, `withhold solve`, `withhold w4`, safe harbor, dual-earner under-withholding |
| 3 | [Twelve PDFs and a coffee](03-importing-documents.md) | `import pdf`, `import status`, the review workflow, owner assignment, provenance |
| 4 | [Freelancer, four payments a year](04-freelancer-quarterly.md) | self-employment tax, QBI, `withhold estimates`, the annualized income installment method |
| 5 | [Should we convert to Roth?](05-scenarios-and-sweeps.md) | `scenario` in full — patches, templates, `compare`, `sweep`, cliffs, assertions |
| 6 | [December, and a losing position](06-harvesting-losses.md) | `harvest import/scan/simulate/washsale-check`, wash sales, DRIP and IRA traps, deferral honesty |
| 7 | [The refund that isn't a refund](07-credits-and-dependents.md) | the credit cascade — care, AOTC, LLC, saver's, CTC/ODC, ACTC, EITC |
| 8 | [Half a year in two states](08-moving-states.md) | part-year residency, `former_state`, localities, jurisdiction overrides, AMT credit carryforward |
| 9 | [Asking the CPA](09-the-ai-cpa.md) | `ask`, `agent --review`, the tool sandbox, guardrails, the privacy model |
| 10 | [Under the hood](10-data-config-and-automation.md) | `data`, `config`, custom tax data, JSON/CSV output, exit codes, scripting |

---

## Before you start

```bash
python3 -m venv ~/.venvs/ouch
source ~/.venvs/ouch/bin/activate
pip install .

ouch --version
```

Vignette 3 needs `pip install "ouch[pdf]"`; vignette 9 needs
`pip install "ouch[ai]"` and an API key. Everything else works with the base
install.

Every vignette is self-contained: it shows the profile it starts from, so you
can copy it into `~/.config/ouch/profiles/` and follow along. If you would
rather not disturb your own setup, point `ouch` somewhere else for the session:

```bash
export XDG_CONFIG_HOME=/tmp/ouch-tutorial/config
export XDG_DATA_HOME=/tmp/ouch-tutorial/data
```

When you want the reference rather than the story, see the
[user manual](../MANUAL.md).

These vignettes expand on [§18 of the specification](../SPEC.md#18-user-vignettes-tutorials),
which sketches the same idea against the design rather than the build. Where the
two differ, these are the ones that ran.

> **Estimates only. `ouch` is not tax advice and does not prepare or file
> returns.** Consult a licensed tax professional before acting on anything you
> read here.
