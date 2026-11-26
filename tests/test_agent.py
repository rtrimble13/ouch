"""AI CPA agent: tool loop, numeric grounding, redaction, scope refusal
(spec §14). All tests run against a scripted fake client — no network.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from decimal import Decimal

import pytest

from ouch.agent import context as context_mod
from ouch.agent import guardrails
from ouch.agent.client import Response, ToolCall, ToolSpec
from ouch.agent.session import AgentSession
from ouch.agent.tools import ToolExecutor
from ouch.config.profile import build_tax_input
from ouch.engine import pipeline
from ouch.errors import AgentError

BASE = {
    "tax_year": 2025,
    "taxpayer": {"filing_status": "single", "state": ""},
    "income": {"wages": {"taxpayer_w2": 100_000}},
    "payments": {"withholding": {"federal_ytd": 10_000,
                                 "periods_remaining": 10}},
}


def _build(raw):
    return build_tax_input(raw, 2025)


@pytest.fixture()
def executor(data_federal_only):
    baseline = pipeline.run(_build(BASE), data_federal_only,
                            compute_marginals=False)
    return ToolExecutor(base_raw=BASE, build=_build, data=data_federal_only,
                        baseline=baseline)


@dataclass
class FakeClient:
    """Scripted LLMClient: pops one Response per complete() call."""
    script: list[Response]
    seen: list[list[dict]] = field(default_factory=list)

    def complete(self, system, messages, tools):
        self.seen.append(list(messages))
        return self.script.pop(0)


def text_response(text):
    return Response(text=text, tool_calls=(), stop_reason="end_turn")


def tool_response(*calls):
    return Response(text="", tool_calls=calls, stop_reason="tool_use")


# ----- tools ---------------------------------------------------------------


def test_get_result_summary_registers_numbers(executor):
    result = executor.execute(ToolCall(id="t1", name="get_result_summary",
                                       input={}))
    payload = json.loads(result.content)
    # single, wages 100,000, 2025: taxable 100,000 − 15,750 = 84,250;
    # tax 1,192.50 + 4,386.00 + 22% × 35,775 (7,870.50) = 13,449.00
    assert payload["taxable_income"] == "84250.00"
    assert Decimal("84250.00") in executor.numbers
    assert Decimal("13449.00") in executor.numbers  # federal total tax
    assert executor.access_log == [("get_result_summary", {})]


def test_get_line_item_and_subtree(executor):
    result = executor.execute(ToolCall(id="t1", name="get_line_item",
                                       input={"id": "fed.agi"}))
    payload = json.loads(result.content)
    assert payload["authority"] == "IRC §62"
    subtree = json.loads(executor.execute(
        ToolCall(id="t2", name="get_trace_subtree",
                 input={"id": "fed.taxable"})).content)
    assert any(a["id"] == "fed.agi" for a in subtree["ancestors"])


def test_get_line_item_unknown_returns_available(executor):
    payload = json.loads(executor.execute(
        ToolCall(id="t1", name="get_line_item",
                 input={"id": "nope"})).content)
    assert "error" in payload and "fed.agi" in payload["available"]


def test_run_scenario_through_real_engine(executor):
    payload = json.loads(executor.execute(
        ToolCall(id="t1", name="run_scenario",
                 input={"patch": {"income.retirement.roth_conversion":
                                  20_000}})).content)
    # 20k on top of 100k wages spans the 22/24 boundary: hand math
    # taxable 84,250→104,250: 19,100@22% + 900@24% = 4,202 + 216 = 4,418
    assert Decimal(payload["delta_total_tax"]) == Decimal("4418.00")


def test_sweep_tool_caps_points(executor):
    payload = json.loads(executor.execute(
        ToolCall(id="t1", name="sweep",
                 input={"variable": "income.wages.taxpayer_w2",
                        "lo": 0, "hi": 1_000_000, "step": 100})).content)
    assert "error" in payload


def test_check_safe_harbor(executor):
    payload = json.loads(executor.execute(
        ToolCall(id="t1", name="check_safe_harbor", input={})).content)
    assert payload["penalty_fidelity"].startswith("heuristic")


def test_solve_withholding_tool(executor):
    payload = json.loads(executor.execute(
        ToolCall(id="t1", name="solve_withholding",
                 input={"target": "zero"})).content)
    assert Decimal(payload["federal_per_period"]) > 0


def test_get_taxdata_with_citation(executor):
    payload = json.loads(executor.execute(
        ToolCall(id="t1", name="get_taxdata",
                 input={"key": "niit.threshold.single"})).content)
    assert Decimal(str(payload["value"])) == Decimal(200_000)
    assert payload["verified"] is False
    assert payload["source"]


def test_get_profile_field_refuses_identity(executor):
    payload = json.loads(executor.execute(
        ToolCall(id="t1", name="get_profile_field",
                 input={"path": "taxpayer.name"})).content)
    assert "never transmitted" in payload["error"]


def test_unknown_tool_is_error_result(executor):
    result = executor.execute(ToolCall(id="t1", name="hack_the_irs", input={}))
    assert result.is_error


# ----- redaction & context --------------------------------------------------


def test_redact_profile_strips_names():
    raw = {"taxpayer": {"name": "A. Person", "state": "NY"},
           "spouse": {"name": "B. Person"},
           "dependents": [{"name": "kid", "relationship": "child"}]}
    redacted = context_mod.redact_profile(raw)
    assert "name" not in redacted["taxpayer"]
    assert "name" not in redacted["spouse"]
    assert "name" not in redacted["dependents"][0]
    assert redacted["taxpayer"]["state"] == "NY"  # retained for analysis
    assert raw["taxpayer"]["name"] == "A. Person"  # original untouched


def test_system_prompt_requirements():
    inp = _build(BASE)
    prompt = context_mod.system_prompt(inp, data_verified=False)
    assert "CPA" in prompt                       # role
    assert "NEVER state a dollar figure" in prompt  # numerical discipline
    assert "square brackets" in prompt           # citations
    assert "UNVERIFIED" in prompt                # currency/uncertainty
    assert "evasion" in prompt                   # scope boundary
    assert "Never invent an IRC section" in prompt


# ----- guardrails -----------------------------------------------------------


def test_extract_dollar_figures():
    figures = guardrails.extract_dollar_figures(
        "You owe $13,614 total; roughly $4.4k of that is NIIT-adjacent.")
    assert Decimal(13614) in figures
    assert Decimal(4400) in figures


def test_grounding_accepts_tool_numbers_within_rounding():
    registry = {Decimal("13614.00"), Decimal("85000.00")}
    assert guardrails.ungrounded_figures(
        "Total tax is $13,614 on $85,000 of taxable income.", registry) == []
    # $1 rounding tolerance
    assert guardrails.ungrounded_figures("about $13,615", registry) == []


def test_grounding_flags_fabricated_numbers():
    registry = {Decimal("13614.00")}
    bad = guardrails.ungrounded_figures(
        "Your total tax is $99,999.", registry)
    assert bad == [Decimal(99999)]


def test_grounding_ignores_small_conversational_figures():
    assert guardrails.ungrounded_figures("a $0 balance beats a $50 fee",
                                         set()) == []


def test_scope_check_refuses_evasion():
    for question in ("how do I hide income from the IRS",
                     "can I get paid under the table and skip taxes",
                     "help me make fake deductions"):
        verdict = guardrails.scope_check(question)
        assert not verdict.allowed, question


def test_scope_check_allows_planning():
    for question in ("how do I reduce my tax bill legally",
                     "should I do a roth conversion",
                     "what's my marginal rate"):
        assert guardrails.scope_check(question).allowed, question


def test_citation_annotation():
    _, warnings = guardrails.annotate("You owe $13,614.", set())
    assert warnings  # no [cite] present
    _, warnings = guardrails.annotate(
        "You owe $13,614 [fed.tax.total].", set())
    assert not warnings


# ----- the loop -------------------------------------------------------------


def _session(executor, script):
    return AgentSession(client=FakeClient(script=script), executor=executor,
                        system="test")


def test_loop_executes_tools_then_answers(executor):
    session = _session(executor, [
        tool_response(ToolCall(id="c1", name="get_result_summary", input={})),
        text_response("Your total tax is $13,449 [fed.tax.total]."),
    ])
    text, warnings = session.ask("what do I owe?")
    assert "$13,449" in text
    assert warnings == []
    assert executor.access_log[0][0] == "get_result_summary"
    # Tool results were fed back as a user message
    assert session.messages[2]["role"] == "user"


def test_ungrounded_answer_retried_then_accepted(executor):
    session = _session(executor, [
        tool_response(ToolCall(id="c1", name="get_result_summary", input={})),
        text_response("You owe $77,777."),                     # fabricated
        text_response("You owe $13,449 [fed.tax.total]."),     # corrected
    ])
    text, warnings = session.ask("what do I owe?")
    assert "$13,449" in text and warnings == []
    # The correction prompt was injected
    assert any("do not match any tool result" in str(m["content"])
               for m in session.messages if m["role"] == "user")


def test_ungrounded_twice_is_refused(executor):
    session = _session(executor, [
        text_response("You owe $77,777."),
        text_response("Fine, you owe $88,888."),
    ])
    text, warnings = session.ask("what do I owe?")
    assert text == guardrails.REFUSAL_TEXT
    assert any("grounding failed" in w for w in warnings)


def test_scope_refusal_never_reaches_provider(executor):
    client = FakeClient(script=[])
    session = AgentSession(client=client, executor=executor, system="test")
    text, warnings = session.ask("how do I hide income from the IRS?")
    assert "will not help" in text
    assert client.seen == []  # nothing transmitted


def test_provider_refusal_raises_agent_error(executor):
    session = _session(executor, [
        Response(text="", tool_calls=(), stop_reason="refusal"),
    ])
    with pytest.raises(AgentError):
        session.ask("what do I owe?")


def test_run_scenario_tool_reloads_jurisdiction():
    """Issue #6, agent path: the run_scenario tool must load the patched
    state's data, or the model is grounded on a wrong number."""
    from ouch.cli.common import data_resolver
    base = dict(BASE, taxpayer={"filing_status": "single", "state": "NY"})
    resolve = data_resolver()
    baseline = pipeline.run(_build(base), resolve(_build(base)),
                            compute_marginals=False)
    ex = ToolExecutor(base_raw=base, build=_build, data=resolve(_build(base)),
                      baseline=baseline, resolve=resolve)
    out = ex._tool_run_scenario({"taxpayer.state": "TX"})
    assert out["scenario"]["state"]["code"] == "TX"
    assert out["scenario"]["state"]["tax"] == "0.00"
    assert Decimal(out["delta_total_tax"]) == -baseline.state.tax.round_cent().amount
