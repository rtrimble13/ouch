"""Tools exposed to the model (spec §14.4).

The model cannot see raw profile data by default; it must request it through
tools, which produces an auditable trail of exactly what was accessed. Every
numeric value returned by a tool is registered so guardrails can verify that
each figure in the response traces to engine output.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any, Callable

from ouch.agent.client import ToolCall, ToolResult, ToolSpec
from ouch.engine import pipeline, solver
from ouch.engine.pipeline import ResolvedData
from ouch.errors import OuchError
from ouch.model.input import TaxInput
from ouch.model.money import Money, ZERO
from ouch.model.result import TaxResult
from ouch.render.json_out import result_to_dict
from ouch.scenario.model import apply_patch, get_path
from ouch.scenario.runner import result_metric
from ouch.taxdata import loader

MAX_SWEEP_POINTS = 30

TOOL_SPECS: list[ToolSpec] = [
    ToolSpec(
        name="get_result_summary",
        description="Top-level TaxResult fields for the user's current "
                    "profile: income, deductions, per-jurisdiction tax, "
                    "rates, balance due. Call this before citing any figure.",
        input_schema={"type": "object", "properties": {},
                      "additionalProperties": False},
    ),
    ToolSpec(
        name="get_line_item",
        description="One computation-trace line with its authority (IRC "
                    "section / form reference) and derivation rule. Ids look "
                    "like 'fed.agi', 'fed.tax.preferential', 'ny.taxable'.",
        input_schema={"type": "object",
                      "properties": {"id": {"type": "string"}},
                      "required": ["id"], "additionalProperties": False},
    ),
    ToolSpec(
        name="get_trace_subtree",
        description="A trace line plus every upstream line that fed it — the "
                    "full derivation of a number.",
        input_schema={"type": "object",
                      "properties": {"id": {"type": "string"}},
                      "required": ["id"], "additionalProperties": False},
    ),
    ToolSpec(
        name="run_scenario",
        description="Execute a what-if through the real engine. `patch` maps "
                    "dotted profile paths to new values, e.g. "
                    "{\"income.retirement.roth_conversion\": 50000}. Returns "
                    "the scenario result and the delta versus baseline. Use "
                    "this to answer any 'should I…' question with real "
                    "numbers instead of estimating.",
        input_schema={"type": "object",
                      "properties": {"patch": {"type": "object"}},
                      "required": ["patch"], "additionalProperties": False},
    ),
    ToolSpec(
        name="sweep",
        description="Marginal analysis: evaluate one profile variable across "
                    "a range through the real engine. Reveals cliffs.",
        input_schema={"type": "object",
                      "properties": {
                          "variable": {"type": "string"},
                          "lo": {"type": "number"},
                          "hi": {"type": "number"},
                          "step": {"type": "number"},
                      },
                      "required": ["variable", "lo", "hi", "step"],
                      "additionalProperties": False},
    ),
    ToolSpec(
        name="check_safe_harbor",
        description="Payment adequacy: safe-harbor requirement, projected "
                    "payments, shortfall, and estimated penalty.",
        input_schema={"type": "object", "properties": {},
                      "additionalProperties": False},
    ),
    ToolSpec(
        name="solve_withholding",
        description="Invoke the bisection solver. target is 'zero', "
                    "'safe-harbor', or a number (positive = owe that much, "
                    "negative = refund). Returns per-period federal "
                    "withholding.",
        input_schema={"type": "object",
                      "properties": {"target": {"type": ["string", "number"]}},
                      "required": ["target"], "additionalProperties": False},
    ),
    ToolSpec(
        name="list_harvest_candidates",
        description="Tax-loss harvesting candidates from the user's imported "
                    "portfolio, with pipeline-computed benefits and wash-sale "
                    "risk.",
        input_schema={"type": "object", "properties": {},
                      "additionalProperties": False},
    ),
    ToolSpec(
        name="get_taxdata",
        description="Look up a threshold/rate in the loaded federal tax data "
                    "file with its citation, e.g. key='niit.threshold' or "
                    "'credits.child_tax_credit'.",
        input_schema={"type": "object",
                      "properties": {"key": {"type": "string"}},
                      "required": ["key"], "additionalProperties": False},
    ),
    ToolSpec(
        name="get_profile_field",
        description="Explicit, logged, redaction-aware read of one profile "
                    "field by dotted path. Identity fields (names) are never "
                    "returned.",
        input_schema={"type": "object",
                      "properties": {"path": {"type": "string"}},
                      "required": ["path"], "additionalProperties": False},
    ),
]

_REDACTED_PATHS = ("name",)  # identity is not sent; amounts are (spec §14.7)


@dataclass
class ToolExecutor:
    """Dispatches tool calls against the pure engine and records everything.

    `numbers` is the grounding registry: every numeric value that has been
    returned to the model. `access_log` is the auditable trail (spec §14.4).
    """

    base_raw: dict
    build: Callable[[dict], TaxInput]
    data: ResolvedData
    baseline: TaxResult
    numbers: set[Decimal] = field(default_factory=set)
    access_log: list[tuple[str, dict]] = field(default_factory=list)

    def specs(self) -> list[ToolSpec]:
        return TOOL_SPECS

    # ----- numeric registry -------------------------------------------------

    def _register(self, node: Any) -> Any:
        if isinstance(node, dict):
            for v in node.values():
                self._register(v)
        elif isinstance(node, list):
            for v in node:
                self._register(v)
        elif isinstance(node, bool):
            pass
        elif isinstance(node, (int, float, Decimal)):
            self._register_number(Decimal(str(node)))
        elif isinstance(node, str):
            try:
                self._register_number(Decimal(node.replace(",", "")))
            except InvalidOperation:
                pass
        return node

    def _register_number(self, value: Decimal) -> None:
        self.numbers.add(value.quantize(Decimal("0.01")))
        self.numbers.add(abs(value).quantize(Decimal("0.01")))
        self.numbers.add(value.quantize(Decimal("1")))
        self.numbers.add(abs(value).quantize(Decimal("1")))

    # ----- dispatch ---------------------------------------------------------

    def execute(self, call: ToolCall) -> ToolResult:
        self.access_log.append((call.name, dict(call.input)))
        handler = getattr(self, f"_tool_{call.name}", None)
        if handler is None:
            return ToolResult(tool_call_id=call.id,
                              content=f"unknown tool '{call.name}'",
                              is_error=True)
        try:
            payload = handler(**call.input)
        except OuchError as e:
            return ToolResult(tool_call_id=call.id,
                              content=f"{type(e).__name__}: {e.message}",
                              is_error=True)
        except TypeError as e:
            return ToolResult(tool_call_id=call.id,
                              content=f"bad tool input: {e}", is_error=True)
        self._register(payload)
        return ToolResult(tool_call_id=call.id,
                          content=json.dumps(payload, default=str))

    # ----- tools ------------------------------------------------------------

    def _tool_get_result_summary(self) -> dict:
        summary = result_to_dict(self.baseline)
        summary["fidelity"] = str(self.baseline.fidelity)
        summary["warnings"] = list(self.baseline.warnings)
        return summary

    def _item_dict(self, item) -> dict:
        return {"id": item.id, "label": item.label,
                "amount": f"{item.amount.round_cent().amount:.2f}",
                "jurisdiction": item.jurisdiction, "rule": item.rule,
                "form_ref": item.form_ref, "authority": item.authority,
                "inputs": list(item.inputs), "fidelity": str(item.fidelity)}

    def _tool_get_line_item(self, id: str) -> dict:
        if not self.baseline.trace.has(id):
            available = sorted(i.id for i in self.baseline.trace.items)
            return {"error": f"no line item '{id}'", "available": available}
        return self._item_dict(self.baseline.trace.get(id))

    def _tool_get_trace_subtree(self, id: str) -> dict:
        if not self.baseline.trace.has(id):
            available = sorted(i.id for i in self.baseline.trace.items)
            return {"error": f"no line item '{id}'", "available": available}
        item = self.baseline.trace.get(id)
        return {"line": self._item_dict(item),
                "ancestors": [self._item_dict(a)
                              for a in self.baseline.trace.ancestors(id)]}

    def _tool_run_scenario(self, patch: dict) -> dict:
        patched = apply_patch(self.base_raw, patch)
        result = pipeline.run(self.build(patched), self.data,
                              compute_marginals=True)
        delta = (result.total_tax_all_jurisdictions
                 - self.baseline.total_tax_all_jurisdictions)
        return {
            "patch": {k: str(v) for k, v in patch.items()},
            "scenario": result_to_dict(result),
            "delta_total_tax": f"{delta.round_cent().amount:.2f}",
            "baseline_total_tax":
                f"{self.baseline.total_tax_all_jurisdictions.round_cent().amount:.2f}",
        }

    def _tool_sweep(self, variable: str, lo: float, hi: float,
                    step: float) -> dict:
        lo_d, hi_d, step_d = (Decimal(str(lo)), Decimal(str(hi)),
                              Decimal(str(step)))
        if step_d <= 0 or hi_d < lo_d:
            return {"error": "range must satisfy lo <= hi, step > 0"}
        n = int((hi_d - lo_d) / step_d) + 1
        if n > MAX_SWEEP_POINTS:
            return {"error": f"{n} points exceeds the {MAX_SWEEP_POINTS}-point "
                             "limit; use a coarser step"}
        from ouch.scenario.runner import sweep as run_sweep
        points = run_sweep(self.base_raw, variable, lo_d, hi_d, step_d,
                           ["total_tax_all_jurisdictions"], self.data,
                           self.build)
        return {"variable": variable, "points": [
            {"value": str(p.value), "total_tax": str(p.total_tax),
             "step_marginal": None if p.step_marginal is None
             else str(p.step_marginal), "cliff": p.cliff}
            for p in points]}

    def _tool_check_safe_harbor(self) -> dict:
        sh = self.baseline.safe_harbor
        if sh is None:
            return {"error": "no safe-harbor analysis available"}
        return {
            "current_year_90pct": f"{sh.current_year_90pct.round_cent().amount:.2f}",
            "prior_year_requirement":
                None if sh.prior_year_pct is None
                else f"{sh.prior_year_pct.round_cent().amount:.2f}",
            "prior_year_pct_label": sh.prior_year_pct_label,
            "required": None if sh.required is None
            else f"{sh.required.round_cent().amount:.2f}",
            "projected_federal_payments":
                f"{sh.projected_federal_payments.round_cent().amount:.2f}",
            "met": sh.met,
            "shortfall": f"{sh.shortfall.round_cent().amount:.2f}",
            "estimated_penalty":
                f"{sh.estimated_penalty.round_cent().amount:.2f}",
            "penalty_fidelity": "heuristic (Form 2210 approximation)",
        }

    def _tool_solve_withholding(self, target) -> dict:
        inp = self.build(self.base_raw)
        if target == "safe-harbor":
            per_period = solver.solve_safe_harbor(inp, self.data)
            label = "meet the federal safe harbor"
        else:
            goal = ZERO if target == "zero" else Money(str(target))
            per_period = solver.solve_withholding(inp, self.data, goal)
            label = f"reach a balance of {goal.round_dollar().amount:,.0f}"
        current = Money(inp.payments.withholding.federal_per_period)
        return {
            "target": str(target), "goal": label,
            "federal_per_period": f"{per_period.round_cent().amount:.2f}",
            "current_per_period": f"{current.round_cent().amount:.2f}",
            "change_per_period":
                f"{(per_period - current).round_cent().amount:.2f}",
            "periods_remaining": inp.payments.withholding.periods_remaining,
        }

    def _tool_list_harvest_candidates(self) -> dict:
        import datetime as _dt
        from ouch.harvest import lots as lots_mod
        from ouch.harvest import ranker
        try:
            portfolio = lots_mod.load_portfolio()
        except OuchError:
            return {"error": "no portfolio on file",
                    "hint": "the user can run `ouch harvest import LOTS.csv`"}
        as_of = max(lot.as_of for lot in portfolio)
        candidates, excluded = ranker.scan(portfolio, self.base_raw,
                                           self.data, self.build, as_of=as_of)
        return {"as_of": as_of.isoformat(), "candidates": [
            {"symbol": c.lot.symbol, "lot_id": c.lot.lot_id,
             "character": c.character,
             "unrealized": f"{c.unrealized.round_cent().amount:.2f}",
             "tax_benefit": f"{c.tax_benefit.round_cent().amount:.2f}",
             "wash_sale_clear": c.wash.clear,
             "wash_sale_permanent": c.wash.permanent}
            for c in candidates],
            "excluded": [{"lot_id": c.lot.lot_id,
                          "reason": c.excluded_reason} for c in excluded]}

    def _tool_get_taxdata(self, key: str) -> dict:
        inp = self.build(self.base_raw)
        doc = loader.raw_file("federal", "", inp.tax_year)
        node: Any = doc
        for part in key.split("."):
            if not isinstance(node, dict) or part not in node:
                return {"error": f"key '{key}' not found in federal "
                                 f"{inp.tax_year} data"}
            node = node[part]
        meta = doc.get("meta", {})
        return {"key": key, "value": node, "year": inp.tax_year,
                "verified": meta.get("verified", False),
                "source": meta.get("source", [])}

    def _tool_get_profile_field(self, path: str) -> dict:
        leaf = path.rsplit(".", 1)[-1]
        if leaf in _REDACTED_PATHS:
            return {"error": f"'{path}' is an identity field and is never "
                             "transmitted (redaction policy)"}
        value = get_path(self.base_raw, path, None)
        if value is None:
            return {"path": path, "value": None,
                    "note": "not set in the profile"}
        if isinstance(value, dict):
            value = {k: v for k, v in value.items()
                     if k not in _REDACTED_PATHS}
        return {"path": path, "value": value}
