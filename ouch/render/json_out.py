"""Machine-readable output (spec appendix C). Stable, versioned schema:
consumers should key on `id`, never on ordering.
"""

from __future__ import annotations

import json
from typing import Any

import ouch
from ouch import DISCLAIMER
from ouch.model.money import Money
from ouch.model.result import TaxResult

JSON_SCHEMA_VERSION = 1


def _m(m: Money) -> str:
    return f"{m.round_cent().amount:.2f}"


def result_to_dict(result: TaxResult) -> dict[str, Any]:
    r: dict[str, Any] = {
        "total_income": _m(result.total_income),
        "agi": _m(result.agi),
        "deduction_taken": _m(result.deduction_taken),
        "deduction_mode": result.deduction_mode,
        "qbi_deduction": _m(result.qbi_deduction),
        "taxable_income": _m(result.taxable_income),
        "tax_ordinary": _m(result.tax_ordinary),
        "tax_preferential": _m(result.tax_preferential),
        "amt_additional": _m(result.amt_additional),
        "se_tax": _m(result.se_tax),
        "additional_medicare": _m(result.additional_medicare),
        "niit": _m(result.niit),
        "credits_nonrefundable": _m(result.credits_nonrefundable),
        "credits_refundable": _m(result.credits_refundable),
        "federal_total_tax": _m(result.federal_total_tax),
        "state": None,
        "local": None,
        "total_tax_all_jurisdictions": _m(result.total_tax_all_jurisdictions),
        "total_payments": _m(result.total_payments),
        "balance_due_or_refund": _m(result.balance_due_or_refund),
        "effective_rate_agi": str(result.effective_rate_agi),
        "effective_rate_gross": str(result.effective_rate_gross),
        "effective_rate_taxable": str(result.effective_rate_taxable),
        "marginal_rate_federal": str(result.marginal_rate_federal),
        "marginal_rate_combined": str(result.marginal_rate_combined),
        "average_rate_by_jurisdiction": {
            k: str(v) for k, v in result.average_rate_by_jurisdiction.items()},
    }
    if result.state is not None:
        r["state"] = {
            "code": result.state.code,
            "agi": _m(result.state.agi),
            "deduction": _m(result.state.deduction),
            "taxable": _m(result.state.taxable),
            "tax": _m(result.state.tax),
        }
    if result.local is not None:
        r["local"] = {
            "name": result.local.name,
            "taxable": _m(result.local.taxable),
            "tax": _m(result.local.tax),
        }
    if result.safe_harbor is not None:
        sh = result.safe_harbor
        r["safe_harbor"] = {
            "current_year_90pct": _m(sh.current_year_90pct),
            "prior_year_requirement":
                _m(sh.prior_year_pct) if sh.prior_year_pct is not None else None,
            "required": _m(sh.required) if sh.required is not None else None,
            "projected_federal_payments": _m(sh.projected_federal_payments),
            "met": sh.met,
            "shortfall": _m(sh.shortfall),
            "estimated_penalty": _m(sh.estimated_penalty),
        }
    return r


def render_json(result: TaxResult, *, include_trace: bool = True) -> str:
    doc = {
        "ouch_version": ouch.__version__,
        "schema_version": JSON_SCHEMA_VERSION,
        "tax_year": result.year,
        "input_fingerprint": result.input_fingerprint,
        "fidelity": str(result.fidelity),
        "result": result_to_dict(result),
        "trace": [
            {
                "id": item.id,
                "label": item.label,
                "amount": _m(item.amount),
                "jurisdiction": item.jurisdiction,
                "form_ref": item.form_ref,
                "authority": item.authority,
                "rule": item.rule,
                "inputs": list(item.inputs),
                "fidelity": str(item.fidelity),
                "warnings": list(item.warnings),
            }
            for item in result.trace.items
        ] if include_trace else [],
        "warnings": [{"message": w} for w in result.warnings],
        "disclaimer": DISCLAIMER.replace("\n", " "),
    }
    return json.dumps(doc, indent=2)
