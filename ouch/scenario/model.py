"""Scenario model (spec §12.1).

A scenario is a **named patch** against a base profile — never a full copy —
so scenarios stay valid as the base profile is updated through the year.

Patch paths use dotted profile addresses. Values may be:
  absolute   75000, true, "NY"
  relative   "+10%", "-5000", "+2500"
  computed   "= income.wages.taxpayer_w2 * 0.10"
Computed expressions support + - * / and parentheses over numbers and dotted
profile paths; they are parsed by a tiny recursive-descent parser — never
`eval`.
"""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any

from ouch.config.settings import config_dir
from ouch.errors import ProfileError, UsageError


def scenarios_dir() -> Path:
    return config_dir() / "scenarios"


@dataclass(frozen=True)
class Assertion:
    path: str          # e.g. "result.marginal_rate_federal"
    op: str            # lt | le | gt | ge | eq
    value: Decimal


@dataclass(frozen=True)
class Scenario:
    name: str
    base: str = "default"
    description: str = ""
    tags: tuple[str, ...] = ()
    patch: dict[str, Any] = field(default_factory=dict)
    assertions: tuple[Assertion, ...] = ()


def load_scenario(name_or_path: str) -> Scenario:
    p = Path(name_or_path).expanduser()
    if p.suffix != ".toml":
        p = scenarios_dir() / f"{name_or_path}.toml"
    if not p.is_file():
        raise ProfileError(
            f"scenario not found: {p}",
            hint="create one with `ouch scenario new NAME --set PATH=VALUE`")
    try:
        raw = tomllib.loads(p.read_text())
    except tomllib.TOMLDecodeError as e:
        raise ProfileError(f"malformed scenario {p}: {e}") from e
    assertions = []
    for path, spec in raw.get("assert", {}).items():
        if not isinstance(spec, dict) or len(spec) != 1:
            raise ProfileError(
                f"scenario {p}: assert '{path}' must be a single-op table "
                "like {lt = 0.35}")
        op, value = next(iter(spec.items()))
        if op not in ("lt", "le", "gt", "ge", "eq"):
            raise ProfileError(f"scenario {p}: unknown assert op '{op}'")
        assertions.append(Assertion(path=path, op=op,
                                    value=Decimal(str(value))))
    return Scenario(
        name=raw.get("name", p.stem),
        base=raw.get("base", "default"),
        description=raw.get("description", ""),
        tags=tuple(raw.get("tags", ())),
        patch=raw.get("patch", {}),
        assertions=tuple(assertions),
    )


# ---------------------------------------------------------------------------
# Dotted-path access on the raw profile dict
# ---------------------------------------------------------------------------


def get_path(raw: dict, dotted: str, default: Any = None) -> Any:
    node: Any = raw
    for part in dotted.split("."):
        if not isinstance(node, dict) or part not in node:
            return default
        node = node[part]
    return node


def set_path(raw: dict, dotted: str, value: Any) -> None:
    parts = dotted.split(".")
    node = raw
    for part in parts[:-1]:
        nxt = node.get(part)
        if nxt is None:
            nxt = {}
            node[part] = nxt
        if not isinstance(nxt, dict):
            raise UsageError(f"patch path '{dotted}': '{part}' is not a table")
        node = nxt
    node[parts[-1]] = value


# ---------------------------------------------------------------------------
# Computed-expression evaluator (no eval, ever)
# ---------------------------------------------------------------------------

_TOKEN = re.compile(r"\s*(?:(?P<num>\d[\d_]*\.?\d*)|(?P<path>[A-Za-z_][\w.]*)"
                    r"|(?P<op>[-+*/()]))")


class _Parser:
    def __init__(self, text: str, raw: dict):
        self.tokens = self._tokenize(text)
        self.pos = 0
        self.raw = raw

    @staticmethod
    def _tokenize(text: str) -> list[tuple[str, str]]:
        tokens = []
        pos = 0
        while pos < len(text):
            m = _TOKEN.match(text, pos)
            if not m or m.end() == pos:
                raise UsageError(f"cannot parse expression at: '{text[pos:]}'")
            pos = m.end()
            for kind in ("num", "path", "op"):
                if m.group(kind):
                    tokens.append((kind, m.group(kind)))
                    break
        return tokens

    def _peek(self) -> tuple[str, str] | None:
        return self.tokens[self.pos] if self.pos < len(self.tokens) else None

    def _next(self) -> tuple[str, str]:
        tok = self._peek()
        if tok is None:
            raise UsageError("unexpected end of expression")
        self.pos += 1
        return tok

    def parse(self) -> Decimal:
        value = self._expr()
        if self._peek() is not None:
            raise UsageError(f"trailing tokens in expression: {self._peek()[1]}")
        return value

    def _expr(self) -> Decimal:
        value = self._term()
        while (tok := self._peek()) and tok[1] in "+-":
            self._next()
            rhs = self._term()
            value = value + rhs if tok[1] == "+" else value - rhs
        return value

    def _term(self) -> Decimal:
        value = self._factor()
        while (tok := self._peek()) and tok[1] in "*/":
            self._next()
            rhs = self._factor()
            value = value * rhs if tok[1] == "*" else value / rhs
        return value

    def _factor(self) -> Decimal:
        kind, text = self._next()
        if text == "-":
            return -self._factor()
        if text == "+":
            return self._factor()
        if text == "(":
            value = self._expr()
            kind, text = self._next()
            if text != ")":
                raise UsageError("missing ')' in expression")
            return value
        if kind == "num":
            return Decimal(text.replace("_", ""))
        if kind == "path":
            ref = get_path(self.raw, text, None)
            if ref is None:
                raise UsageError(
                    f"expression references '{text}' which is not set in the "
                    "base profile")
            return Decimal(str(ref))
        raise UsageError(f"unexpected token '{text}' in expression")


_RELATIVE = re.compile(r"^(?P<sign>[+-])(?P<num>[\d_]+\.?\d*)(?P<pct>%?)$")


def resolve_patch_value(raw: dict, dotted: str, value: Any) -> Any:
    """Resolve a patch value against the base profile: absolute, relative
    (+10%, -5000), or computed (= expr)."""
    if not isinstance(value, str):
        return value
    text = value.strip()
    if text.startswith("="):
        return str(_Parser(text[1:], raw).parse())
    m = _RELATIVE.match(text)
    if m:
        base = Decimal(str(get_path(raw, dotted, 0) or 0))
        delta = Decimal(m.group("num").replace("_", ""))
        if m.group("pct"):
            delta = base * delta / 100
        return str(base + delta if m.group("sign") == "+" else base - delta)
    return value  # plain string (e.g. a state code or filing status)


def apply_patch(raw: dict, patch: dict[str, Any]) -> dict:
    """Return a deep-copied profile dict with the patch applied."""
    import copy
    out = copy.deepcopy(raw)
    for dotted, value in patch.items():
        set_path(out, dotted, resolve_patch_value(raw, dotted, value))
    return out
