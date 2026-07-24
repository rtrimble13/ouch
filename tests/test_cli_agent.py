"""CLI gating for the AI commands: off by default, --no-ai hard-disable,
missing extra/key messages. No network is ever touched (exit happens first).
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

PROFILE = """\
schema_version = 2
tax_year = 2025

[taxpayer]
filing_status = "single"
state = "TX"

[income.wages]
taxpayer_w2 = 100000
"""


@pytest.fixture()
def home(tmp_path: Path) -> dict:
    config = tmp_path / "config"
    profiles = config / "ouch" / "profiles"
    profiles.mkdir(parents=True)
    (profiles / "default.toml").write_text(PROFILE)
    env = dict(os.environ)
    env.update({"XDG_CONFIG_HOME": str(config),
                "XDG_DATA_HOME": str(tmp_path / "data")})
    env.pop("OUCH_AI_ENABLED", None)
    return env


def run_cli(env, *args):
    return subprocess.run([sys.executable, "-m", "ouch", *args],
                          capture_output=True, text=True, timeout=120,
                          env=env)


def test_ask_disabled_by_default_exit_8(home):
    r = run_cli(home, "ask", "what do I owe?")
    assert r.returncode == 8
    assert "off by default" in r.stderr
    assert "opt in" in r.stderr


def test_no_ai_hard_disables_even_when_enabled(home):
    home["OUCH_AI_ENABLED"] = "1"
    r = run_cli(home, "--no-ai", "ask", "what do I owe?")
    assert r.returncode == 8
    assert "--no-ai" in r.stderr


def test_enabled_but_no_api_key_exit_8(home):
    home["OUCH_AI_ENABLED"] = "1"
    home.pop("ANTHROPIC_API_KEY", None)
    # --yes skips the consent prompt so we reach client construction,
    # which fails on the missing key before any network call.
    r = run_cli(home, "ask", "--yes", "what do I owe?")
    assert r.returncode == 8
    assert "ANTHROPIC_API_KEY" in r.stderr or "not installed" in r.stderr
