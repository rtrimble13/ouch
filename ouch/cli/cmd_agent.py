"""`ouch ask` / `ouch agent` — the AI CPA (spec §14.3, §14.7).

Privacy controls: off by default, explicit confirmation before the first
transmission, --no-ai hard-disables all network paths for a run.
"""

from __future__ import annotations

from typing import Optional

import typer

from ouch import DISCLAIMER
from ouch.agent import context as context_mod
from ouch.agent.client import make_client
from ouch.agent.session import AgentSession
from ouch.agent.tools import ToolExecutor
from ouch.cli.common import Runtime, data_resolver, prepare_raw
from ouch.config import profile as profile_mod
from ouch.engine import pipeline
from ouch.errors import AgentError

REVIEW_PROMPT = (
    "Proactively review my whole tax situation for this year. Identify the "
    "largest exposures and planning opportunities, in priority order, with "
    "the numbers behind each. Check the safe harbor. Cite line items."
)


def _gate(rt: Runtime, assume_yes: bool) -> None:
    if getattr(rt, "no_ai", False):
        raise AgentError(
            "AI is hard-disabled for this run (--no-ai)")
    enabled = rt.settings.get("ai.enabled", False)
    if str(enabled).lower() in ("0", "false", ""):
        raise AgentError(
            "AI is off by default and not enabled",
            hint="set [ai] enabled = true in config.toml, or "
                 "OUCH_AI_ENABLED=1 — nothing is transmitted until you "
                 "opt in")


def _build_session(rt: Runtime, assume_yes: bool) -> AgentSession:
    raw, _ = profile_mod.load_profile_raw(rt.profile_name)
    prepare_raw(rt, raw)
    raw = context_mod.redact_profile(raw)
    build = lambda r: profile_mod.build_tax_input(r, rt.tax_year)  # noqa: E731
    inp = build(raw)
    resolve = data_resolver()
    data = resolve(inp)

    # Explicit confirmation before the first transmission (spec §14.7)
    require_confirm = str(rt.settings.get("ai.require_confirmation",
                                          True)).lower() not in ("0", "false")
    if require_confirm and not assume_yes:
        rt.console().print(
            f"⚠ {context_mod.transmission_notice(rt.settings, inp)}")
        typer.confirm("  Proceed?", abort=True)

    baseline = pipeline.run(inp, data)
    executor = ToolExecutor(base_raw=raw, build=build, data=data,
                            baseline=baseline, resolve=resolve)
    system = context_mod.system_prompt(inp, data.federal.meta.verified)
    client = make_client(rt.settings)
    return AgentSession(client=client, executor=executor, system=system)


def _render_answer(rt: Runtime, text: str, warnings: list[str]) -> None:
    console = rt.console()
    console.print(text)
    for warning in warnings:
        console.print(f"\n  ⚠ {warning}")
    console.print(f"\n[dim]{DISCLAIMER.splitlines()[0]} "
                  f"{DISCLAIMER.splitlines()[2]}[/dim]")


def ask(ctx: typer.Context,
        question: str = typer.Argument(..., help="One-shot question"),
        yes: bool = typer.Option(False, "--yes",
                                 help="Skip the transmission confirmation")) -> None:
    """One-shot AI CPA question, grounded in the engine's numbers."""
    rt: Runtime = ctx.obj
    _gate(rt, yes)
    session = _build_session(rt, yes)
    text, warnings = session.ask(question)
    _render_answer(rt, text, warnings)


def agent(ctx: typer.Context,
          review: bool = typer.Option(False, "--review",
                                      help="Proactive review of the whole "
                                           "profile"),
          yes: bool = typer.Option(False, "--yes",
                                   help="Skip the transmission confirmation")) -> None:
    """Interactive AI CPA session."""
    rt: Runtime = ctx.obj
    _gate(rt, yes)
    session = _build_session(rt, yes)
    console = rt.console()
    console.print(f"ouch AI CPA · profile '{rt.profile_name}' · "
                  f"TY{rt.tax_year} · data: federal "
                  f"{'verified' if session.executor.data.federal.meta.verified else 'unverified'}")
    console.print("Type /quit to exit.\n")

    if review:
        text, warnings = session.ask(REVIEW_PROMPT)
        _render_answer(rt, text, warnings)

    while True:
        try:
            question = typer.prompt(">", prompt_suffix=" ")
        except (typer.Abort, EOFError):
            break
        if question.strip() in ("/quit", "/exit", "quit", "exit"):
            break
        if not question.strip():
            continue
        text, warnings = session.ask(question)
        _render_answer(rt, text, warnings)
        access = len(session.executor.access_log)
        console.print(f"[dim]({access} tool call(s) logged this session)[/dim]")
