"""Provider-agnostic LLM interface (spec §14.2).

Model id, provider, and endpoint are configuration, not code — see `[ai]` in
config.toml. The Anthropic implementation is the reference backend and is
imported lazily so the `[ai]` extra stays optional.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Protocol

from ouch.errors import AgentError


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    input_schema: dict


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    input: dict


@dataclass(frozen=True)
class ToolResult:
    tool_call_id: str
    content: str
    is_error: bool = False


@dataclass(frozen=True)
class Response:
    text: str
    tool_calls: tuple[ToolCall, ...]
    stop_reason: str
    raw_content: Any = None   # provider-native blocks, echoed back verbatim


# Message dicts: {"role": "user"|"assistant", "content": ...} where content is
# a str, a list of ToolResult (tool results going back), or the provider-native
# raw_content from a prior Response (assistant echo).


class LLMClient(Protocol):
    def complete(self, system: str, messages: list[dict],
                 tools: list[ToolSpec]) -> Response: ...


class AnthropicClient:
    """Reference backend. Requires `pip install "ouch[ai]"` and an API key in
    the environment variable named by [ai].api_key_env — ouch never writes a
    key to disk (spec §17.2).
    """

    def __init__(self, model: str, api_key_env: str = "ANTHROPIC_API_KEY",
                 max_tokens: int = 4096):
        try:
            import anthropic  # noqa: F401
        except ImportError as e:
            raise AgentError(
                "AI support is not installed.",
                hint='pip install "ouch[ai]"') from e
        api_key = os.environ.get(api_key_env)
        if not api_key:
            raise AgentError(
                f"no API key found in ${api_key_env}",
                hint=f"export {api_key_env}=... (ouch never stores keys)")
        self._anthropic = anthropic
        self._client = anthropic.Anthropic(api_key=api_key)
        self._model = model
        self._max_tokens = max_tokens

    def _translate(self, messages: list[dict]) -> list[dict]:
        out = []
        for msg in messages:
            content = msg["content"]
            if isinstance(content, list) and content and isinstance(content[0], ToolResult):
                content = [
                    {"type": "tool_result", "tool_use_id": r.tool_call_id,
                     "content": r.content,
                     **({"is_error": True} if r.is_error else {})}
                    for r in content
                ]
            out.append({"role": msg["role"], "content": content})
        return out

    def complete(self, system: str, messages: list[dict],
                 tools: list[ToolSpec]) -> Response:
        try:
            response = self._client.messages.create(
                model=self._model,
                max_tokens=self._max_tokens,
                system=system,
                messages=self._translate(messages),
                tools=[{"name": t.name, "description": t.description,
                        "input_schema": t.input_schema} for t in tools],
            )
        except self._anthropic.AuthenticationError as e:
            raise AgentError(f"AI provider rejected the API key: {e}") from e
        except self._anthropic.RateLimitError as e:
            raise AgentError("AI provider rate limit reached — retry later") from e
        except self._anthropic.APIConnectionError as e:
            raise AgentError(f"cannot reach the AI provider: {e}") from e
        except self._anthropic.APIStatusError as e:
            raise AgentError(f"AI provider error ({e.status_code}): {e.message}") from e

        # Safety classifiers may decline with a normal 200 — check stop_reason
        # before reading content.
        if response.stop_reason == "refusal":
            return Response(text="", tool_calls=(), stop_reason="refusal",
                            raw_content=response.content)
        text = "".join(b.text for b in response.content if b.type == "text")
        calls = tuple(ToolCall(id=b.id, name=b.name, input=dict(b.input))
                      for b in response.content if b.type == "tool_use")
        return Response(text=text, tool_calls=calls,
                        stop_reason=response.stop_reason,
                        raw_content=response.content)


def make_client(settings) -> LLMClient:
    """Build the configured client. Provider and model come from config,
    never from code (spec §14.2)."""
    provider = str(settings.get("ai.provider", "anthropic"))
    model = str(settings.get("ai.model", "claude-opus-5"))
    api_key_env = str(settings.get("ai.api_key_env", "ANTHROPIC_API_KEY"))
    if provider == "anthropic":
        return AnthropicClient(model=model, api_key_env=api_key_env)
    raise AgentError(
        f"unknown AI provider '{provider}'",
        hint="supported providers: anthropic")
