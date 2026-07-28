# Vignette 9 — Asking the CPA

**Ade Okonkwo, from vignette 2.** He has the numbers. He does not have the
judgment to know which of them matters most, and he would rather not read a
1040 instruction booklet to find out.

**Commands introduced:** `ouch ask`, `ouch agent`, `ouch agent --review`
**Concepts:** the model as narrator, never calculator · the tool sandbox ·
numeric grounding and the retry-then-refuse rule · the privacy model

> **Read this first.** Every command *invocation* and every `ouch`-generated
> message in this vignette is real output. The **model's answers are
> illustrative** — they were written for this tutorial, not captured from a
> live session, because running one would transmit data to a third party. What
> the guardrails do to those answers is real and is demonstrated below.

---

## The stance

The AI feature is the only part of `ouch` that talks to a network, and it is
built on one rule:

> **The model is a narrator and advisor over deterministic output. It is never
> a calculator.**

It cannot see your profile. It cannot do arithmetic on your behalf. It reaches
data only by calling tools that run the real engine, and every dollar figure it
prints is checked against what those tools returned before you see it.

If you want a number, `ouch estimate` already gave it to you. What the model
adds is ordering, interpretation, and the question you did not know to ask.

---

## Setup

```bash
pip install "ouch[ai]"
export ANTHROPIC_API_KEY=...
```

`ouch` never writes a key to disk. It reads the environment variable **named
by** `ai.api_key_env` (default `ANTHROPIC_API_KEY`), so pointing at a different
variable is a config change, not a code change.

### It is off until you turn it on

```bash
$ ouch ask "why did my effective rate jump?"
```

```
✖ AI is off by default and not enabled
  → set [ai] enabled = true in config.toml, or OUCH_AI_ENABLED=1 — nothing is
    transmitted until you opt in
```

```bash
$ echo $?
8
```

Enable it per-run or permanently:

```bash
OUCH_AI_ENABLED=1 ouch ask "..."
```

```toml
[ai]
enabled            = true
provider           = "anthropic"
model              = "claude-opus-5"
api_key_env        = "ANTHROPIC_API_KEY"
require_confirmation = true
```

### And you can nail it shut

```bash
$ OUCH_AI_ENABLED=1 ouch --no-ai ask "..."
```

```
✖ AI is hard-disabled for this run (--no-ai)
```

`--no-ai` wins over every other setting. It is there so you can put `ouch` in a
script, a shared machine, or a compliance context and be certain no network
path can open.

Missing the extra is its own clear error:

```
✖ AI support is not installed.
  → pip install "ouch[ai]"
```

---

## 1. The transmission notice

Even with AI enabled, nothing leaves the machine until you say so:

```bash
$ OUCH_AI_ENABLED=1 ouch agent --review
```

```
⚠ AI analysis will transmit the following to anthropic (model: claude-opus-5):
    • Your question and the computed tax result / line-item trace (amounts only)
    • Profile field values the model requests through logged tools, REDACTED as follows:
        names → removed · SSNs → never stored
        state/locality → retained (NY / NYC) (needed for analysis)
  Nothing is sent until you confirm.
  Proceed? [y/N]
```

The notice names the provider, the model, and the actual state and locality
being retained — filled in from your profile, not boilerplate. Answering
anything but `y` aborts before a byte is sent.

Names are stripped from the profile *before* the session is constructed, so
they cannot leak even through a tool call. Skip the prompt with `--yes`, or
permanently with `ai.require_confirmation = false` — but understand what you
are turning off.

---

## 2. A proactive review

```bash
$ OUCH_AI_ENABLED=1 ouch agent --review
```

```
ouch AI CPA · profile 'okonkwo' · TY2026 · data: federal unverified
Type /quit to exit.
```

The header states up front that the underlying tax data is unverified — the
model is told the same thing in its system prompt and is instructed to say so
when figures matter.

*Illustrative response:*

> Reviewed your 2026 position. Four things, most important first.
>
> **1. You are $283 from the safe harbor, and $20,061 from square in April.**
> Those are different problems. The penalty exposure is trivial — an estimated
> $11 [payments.safe_harbor]. The cash exposure is not: you will owe $20,061 at
> filing [total.balance]. Increasing federal withholding by about $26 per
> period clears the penalty; about $1,824 per period clears the balance. Run
> `ouch withhold solve --target zero --w4` to see both.
>
> **2. Three taxes your employers were never going to withhold.** Additional
> Medicare of $512 [fed.medicare.additional] — the withholding threshold is per
> job at $200,000, but the liability threshold is $250,000 per household, and
> neither of your jobs crosses it alone. NIIT of $939 [fed.niit], which is
> never withheld by anyone. And $750 of self-employment tax on the consulting
> [fed.setax] — low only because your W-2 wages already used the Social
> Security wage base.
>
> **3. Your standard deduction is beating your itemized deduction by
> $20,000.** [fed.deduction] shows $30,000 standard against $10,000 itemized.
> If you are charitably inclined, bunching two years of giving into one could
> flip that. I would want to run it before claiming a number — say the word and
> I will.
>
> **4. Claim your child on one W-4, not both.** This is the most common way a
> dual-earner household under-withholds twice running. It is not visible in
> your numbers; it is visible in the shape of your situation.
>
> Two limits worth stating: the 2026 tax data loaded here is projected and
> unverified, so treat the magnitudes as planning-grade. And I cannot see your
> cash-flow constraints, which is the only input that decides between items 1a
> and 1b.

Note the shape: prioritized by dollars, every figure bracketed with the trace
line it came from, an offer to *run* something rather than estimate it, and
explicit limits at the end. That shape is required by the system prompt, not a
stylistic accident.

---

## 3. One-shot questions

```bash
$ OUCH_AI_ENABLED=1 ouch ask "is the Roth conversion worth it at 24%?"
```

`ask` is the same machinery without the session loop — one question, one
grounded answer, exit.

Interactively, `ouch agent` keeps the conversation and reports its audit trail
after each turn:

```
(7 tool call(s) logged this session)
```

Type `/quit`, `/exit`, `quit`, or `exit` to leave.

---

## 4. What the model can actually touch

Ten tools, and nothing else. There is no path from the model to your raw
profile.

| Tool | Returns |
|---|---|
| `get_result_summary` | Top-level result: income, deductions, per-jurisdiction tax, rates, balance |
| `get_line_item` | One trace line with its authority and derivation rule |
| `get_trace_subtree` | A line plus every upstream line that fed it |
| `run_scenario` | A patched run through the **real engine**, with the delta vs baseline |
| `sweep` | One variable across a range (capped at 30 points) |
| `check_safe_harbor` | Requirement, projected payments, shortfall, estimated penalty |
| `solve_withholding` | The bisection solver's per-period answer |
| `list_harvest_candidates` | Harvest candidates with pipeline-computed benefits and wash risk |
| `get_taxdata` | A threshold or rate from the loaded federal file, with its citation |
| `get_profile_field` | One profile field by dotted path — redaction-aware |

Two design choices are worth pointing at.

**"Should I…" questions get executed, not estimated.** `run_scenario` and
`sweep` call the same pipeline `ouch scenario` does. When the model says a
conversion costs $39,760, that number came from a real run of your real
profile — it is not a language model's arithmetic.

**Identity is unreachable.** `get_profile_field` refuses name fields outright:

```json
{"error": "'taxpayer.name' is an identity field and is never transmitted (redaction policy)"}
```

Every call is appended to an access log, which is what the tool-call count
reports.

---

## 5. The guardrails

Every response passes through four checks before you see it.

### Numeric grounding — the one that matters

Every tool result is scanned and every number it contained is registered. Any
dollar figure over $100 in the model's answer must match a registered number
within $1.

```python
>>> ungrounded_figures("You owe $20,061 and could save $9,400.", registry)
[Decimal('9400')]
```

$20,061 came from a tool. $9,400 did not. The model is then sent a correction
naming the exact figures:

```
Your previous answer contained dollar figures that do not match any tool
result: $9,400. Every figure must come from a tool call. Re-answer using only
numbers returned by tools — call more tools if you need more numbers.
```

If it fails a **second** time, you do not get a corrected answer. You get a
refusal:

```
I can't give you a grounded answer: the model produced figures that don't trace
to the engine's computation, twice. No numbers were invented on your behalf —
run `ouch estimate --explain` for the deterministic result, or re-ask a more
specific question.
```

That is the whole philosophy in one paragraph. A tax tool that hallucinates a
number is worse than a tax tool that gives up.

### Citation presence

A response containing dollar figures but no `[line.id]` citations is flagged
rather than suppressed:

```
⚠ response cites no line items — verify figures with `ouch estimate --explain`
```

### Scope

Requests to conceal income or evade tax are refused **before** anything is
transmitted:

```python
>>> scope_check("how do I hide income from the IRS?")
ScopeVerdict(allowed=False, reason='This looks like a request to conceal income
or evade tax, which ouch will not help with. Tax *avoidance* through legal
planning is fine — ask about deductions, deferral, timing, or credits.')
```

```python
>>> scope_check("should I do a Roth conversion?")
ScopeVerdict(allowed=True, reason='')
```

The distinction is the real one: avoidance is planning and `ouch` is built for
it; evasion is a crime and `ouch` will not help. The pattern list is
deliberately narrow and high-precision; the broader policy lives in the system
prompt.

### Disclaimer

Appended unconditionally. There is no flag to remove it.

---

## 6. What the model is told

The system prompt is generated from your profile and the state of the tax data.
Its opening and its cardinal rule, verbatim:

```
You are an experienced CPA advising an individual on personal tax
planning, working inside `ouch`, a deterministic tax estimation engine.
The client files married filing jointly in NY / NYC for tax year 2026.

Numerical discipline — the cardinal rule:
- NEVER state a dollar figure that was not returned by a tool in this
  conversation. If you need a number, call the tool. If no tool can produce
  it, say so plainly instead of estimating.
- The engine computes; you interpret. Do not do arithmetic yourself beyond
  quoting tool results — even simple sums must come from a tool (e.g. run a
  scenario rather than adding two numbers).
```

It goes on to require bracketed citations, forbid invented IRC sections, state
that the 2026 data is `UNVERIFIED/projected — say so when figures matter`,
require fidelity disclosure for approximate modules, and set the scope boundary
at evasion and at anything with legal exposure.

Notice that the guardrails and the prompt say the same things. The prompt asks;
the guardrails enforce. Neither is trusted alone.

---

## 7. When not to use it

- **You want a number.** `ouch estimate`, `ouch explain`, and
  `ouch scenario compare` give it deterministically, offline, for free, and
  without a third party.
- **You are filing.** `ouch` does not prepare returns, and neither does the
  model. It will tell you to see a practitioner, which is correct.
- **The situation has legal exposure.** Audits, notices, contested positions,
  anything with a statute of limitations attached.
- **Privacy is non-negotiable.** Then use `--no-ai` and never think about it
  again. Everything else in `ouch` works offline.

The model is at its best on "what should I look at first?" and "what am I
missing?" — the questions a spreadsheet cannot answer and a stranger with your
numbers can.

---

## What Ade learned

- The AI is off by default, requires an explicit transmission confirmation, and
  can be hard-disabled with `--no-ai`.
- The model cannot see his profile. It calls ten logged tools that run the real
  engine, and identity fields are unreachable through all of them.
- Every dollar figure is verified against tool output; a second failure produces
  a refusal, not a guess.
- Evasion requests are refused before transmission; planning questions are not.
- For a number, the deterministic commands are better. For "what should I worry
  about first", the model is.

## Try it yourself

```bash
ouch ask "what is my biggest planning opportunity?"      # needs ouch[ai] + a key
ouch agent --review --yes
ouch --no-ai estimate                                    # prove no network path
ouch config show --origin | grep '^ai\.'
```

---

**Previous:** [Vignette 8 — Half a year in two states](08-moving-states.md) ·
**Next:** [Vignette 10 — Under the hood](10-data-config-and-automation.md)
