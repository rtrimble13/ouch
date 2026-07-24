"""The agent loop: context assembly → provider call → tool-use loop →
guardrails → render (spec §14.2). Pure orchestration over the LLMClient
protocol so it is testable with a scripted fake client.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ouch.agent import guardrails
from ouch.agent.client import LLMClient, Response
from ouch.agent.tools import ToolExecutor
from ouch.errors import AgentError

MAX_TOOL_ITERATIONS = 12


@dataclass
class AgentSession:
    client: LLMClient
    executor: ToolExecutor
    system: str
    messages: list[dict] = field(default_factory=list)

    def _run_loop(self) -> Response:
        for _ in range(MAX_TOOL_ITERATIONS):
            response = self.client.complete(
                system=self.system, messages=self.messages,
                tools=self.executor.specs())
            if response.stop_reason == "refusal":
                raise AgentError(
                    "the AI provider declined this request "
                    "(safety classifier)")
            self.messages.append({"role": "assistant",
                                  "content": response.raw_content
                                  if response.raw_content is not None
                                  else response.text})
            if response.tool_calls:
                results = [self.executor.execute(call)
                           for call in response.tool_calls]
                self.messages.append({"role": "user", "content": results})
                continue
            return response
        raise AgentError(
            f"tool loop exceeded {MAX_TOOL_ITERATIONS} iterations without a "
            "final answer")

    def ask(self, question: str) -> tuple[str, list[str]]:
        """One turn: scope check → loop → grounding (retry once → refuse) →
        annotation. Returns (text, warnings)."""
        verdict = guardrails.scope_check(question)
        if not verdict.allowed:
            return verdict.reason, ["scope refusal (logged)"]

        self.messages.append({"role": "user", "content": question})
        response = self._run_loop()

        bad = guardrails.ungrounded_figures(response.text,
                                            self.executor.numbers)
        if bad:
            # Strip the response, retry once with a correction (spec §14.6).
            correction = guardrails.CORRECTION_PROMPT.format(
                figures=", ".join(f"${b:,.0f}" for b in bad))
            self.messages.append({"role": "user", "content": correction})
            response = self._run_loop()
            bad = guardrails.ungrounded_figures(response.text,
                                                self.executor.numbers)
            if bad:
                return guardrails.REFUSAL_TEXT, [
                    "numeric grounding failed twice — response refused"]

        return guardrails.annotate(response.text, self.executor.numbers)
