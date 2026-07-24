"""TaxResult, LineItem, ComputationTrace (spec §7.4–7.5)."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Literal, Optional

from ouch.errors import InvariantError
from ouch.model.enums import Fidelity
from ouch.model.money import Money


@dataclass(frozen=True)
class LineItem:
    id: str                    # "fed.agi", "fed.tax.ordinary", "ny.taxable"
    label: str                 # "Adjusted Gross Income"
    amount: Money
    jurisdiction: str          # "federal" | "NY" | "NYC"
    rule: str                  # human-readable derivation
    form_ref: str | None = None      # "1040 line 11"
    authority: str | None = None     # "IRC §62"
    inputs: tuple[str, ...] = ()     # ids of upstream line items — forms a DAG
    fidelity: Fidelity = Fidelity.EXACT
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class ComputationTrace:
    items: tuple[LineItem, ...]

    def get(self, id: str) -> LineItem:
        for item in self.items:
            if item.id == id:
                return item
        raise KeyError(f"no line item with id '{id}'")

    def has(self, id: str) -> bool:
        return any(item.id == id for item in self.items)

    def ancestors(self, id: str) -> list[LineItem]:
        """All upstream line items of `id`, depth-first. Powers `ouch explain`."""
        seen: dict[str, LineItem] = {}
        stack = list(self.get(id).inputs)
        while stack:
            iid = stack.pop()
            if iid in seen or not self.has(iid):
                continue
            item = self.get(iid)
            seen[iid] = item
            stack.extend(item.inputs)
        return list(seen.values())

    def verify_dag(self) -> None:
        """Every declared input exists and the graph is acyclic (spec §15.3)."""
        ids = {item.id for item in self.items}
        deps = {item.id: [i for i in item.inputs if not i.startswith("taxdata")]
                for item in self.items}
        for item in self.items:
            for inp in deps[item.id]:
                if inp not in ids:
                    raise InvariantError(
                        f"trace line '{item.id}' declares unknown input '{inp}'"
                    )
        # Kahn's algorithm for cycle detection
        indeg = {i: 0 for i in ids}
        for iid, ins in deps.items():
            for _ in ins:
                indeg[iid] += 1
        queue = [i for i, d in indeg.items() if d == 0]
        visited = 0
        rev: dict[str, list[str]] = {i: [] for i in ids}
        for iid, ins in deps.items():
            for inp in ins:
                rev[inp].append(iid)
        while queue:
            node = queue.pop()
            visited += 1
            for dep in rev[node]:
                indeg[dep] -= 1
                if indeg[dep] == 0:
                    queue.append(dep)
        if visited != len(ids):
            raise InvariantError("computation trace contains a cycle")


class TraceBuilder:
    """Mutable accumulator used inside the pure pipeline; emits a frozen trace."""

    def __init__(self) -> None:
        self._items: list[LineItem] = []

    def add(self, id: str, label: str, amount: Money, *, jurisdiction: str,
            rule: str, form_ref: str | None = None, authority: str | None = None,
            inputs: tuple[str, ...] = (), fidelity: Fidelity = Fidelity.EXACT,
            warnings: tuple[str, ...] = ()) -> LineItem:
        item = LineItem(
            id=id, label=label, amount=amount.round_cent(),
            jurisdiction=jurisdiction, rule=rule, form_ref=form_ref,
            authority=authority, inputs=inputs, fidelity=fidelity,
            warnings=warnings,
        )
        self._items.append(item)
        return item

    def build(self) -> ComputationTrace:
        trace = ComputationTrace(items=tuple(self._items))
        trace.verify_dag()
        return trace

    def worst_fidelity(self) -> Fidelity:
        if not self._items:
            return Fidelity.EXACT
        return Fidelity.worst(*(i.fidelity for i in self._items))


@dataclass(frozen=True)
class SafeHarborResult:
    current_year_90pct: Money
    prior_year_pct: Optional[Money]      # 100% or 110% of prior-year tax
    prior_year_pct_label: str            # "100%" | "110%"
    required: Optional[Money]            # min of the applicable tests
    projected_federal_payments: Money
    met: Optional[bool]                  # None when prior-year data missing
    shortfall: Money
    estimated_penalty: Money


@dataclass(frozen=True)
class StateResult:
    code: str
    starting_income: Money
    agi: Money
    deduction: Money
    exemptions: Money
    taxable: Money
    tax: Money
    credits: Money


@dataclass(frozen=True)
class LocalResult:
    name: str
    taxable: Money
    tax: Money
    credits: Money


@dataclass(frozen=True)
class TaxResult:
    year: int
    input_fingerprint: str

    # Federal
    total_income: Money
    agi: Money
    deduction_taken: Money
    deduction_mode: Literal["standard", "itemized"]
    qbi_deduction: Money
    taxable_income: Money
    tax_ordinary: Money
    tax_preferential: Money
    amt_additional: Money
    se_tax: Money
    additional_medicare: Money
    niit: Money
    credits_nonrefundable: Money
    credits_refundable: Money
    federal_total_tax: Money

    # State / local
    state: Optional[StateResult]
    local: Optional[LocalResult]

    # Aggregates
    total_tax_all_jurisdictions: Money
    total_payments: Money
    balance_due_or_refund: Money         # negative = refund

    effective_rate_agi: Decimal
    effective_rate_gross: Decimal
    effective_rate_taxable: Decimal
    marginal_rate_federal: Decimal
    marginal_rate_combined: Decimal      # fed + state + local + FICA/NIIT on next $
    average_rate_by_jurisdiction: dict[str, Decimal] = field(default_factory=dict)

    safe_harbor: Optional[SafeHarborResult] = None
    trace: ComputationTrace = ComputationTrace(items=())
    fidelity: Fidelity = Fidelity.EXACT  # worst across all lines
    warnings: tuple[str, ...] = ()
    other_state: Optional[StateResult] = None  # part-year former residence
