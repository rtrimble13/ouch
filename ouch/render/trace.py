"""Trace rendering for `ouch explain` and `--explain` (spec P2, §8.3)."""

from __future__ import annotations

from rich.console import Console
from rich.tree import Tree

from ouch.model.result import ComputationTrace, LineItem


def _describe(item: LineItem) -> str:
    parts = [f"[bold]{item.id}[/bold] · $ {item.amount.round_dollar().amount:,.0f}"
             f" · {item.label}"]
    return " ".join(parts)


def _details(item: LineItem, show_citations: bool) -> list[str]:
    out = []
    if show_citations and (item.authority or item.form_ref):
        cite = " · ".join(x for x in (item.authority, item.form_ref) if x)
        out.append(f"[dim]Authority: {cite}[/dim]")
    out.append(f"[dim]Rule: {item.rule}[/dim]")
    if item.fidelity.value != "exact":
        out.append(f"[yellow]fidelity: {item.fidelity}[/yellow]")
    for w in item.warnings:
        out.append(f"[yellow]⚠ {w}[/yellow]")
    return out


def render_explain(trace: ComputationTrace, line_id: str, *,
                   show_citations: bool = True,
                   console: Console | None = None) -> None:
    console = console or Console()
    root_item = trace.get(line_id)
    tree = Tree(_describe(root_item))
    for detail in _details(root_item, show_citations):
        tree.add(detail)

    def add_children(node: Tree, item: LineItem, depth: int) -> None:
        if depth > 6:
            return
        for input_id in item.inputs:
            if not trace.has(input_id):
                node.add(f"[dim]{input_id} (data reference)[/dim]")
                continue
            child_item = trace.get(input_id)
            child = node.add(_describe(child_item))
            for detail in _details(child_item, show_citations):
                child.add(detail)
            add_children(child, child_item, depth + 1)

    add_children(tree, root_item, 0)
    console.print(tree)


def render_full_trace(trace: ComputationTrace, *,
                      console: Console | None = None) -> None:
    console = console or Console()
    for item in trace.items:
        console.print(_describe(item))
        console.print(f"  [dim]{item.rule}[/dim]")
