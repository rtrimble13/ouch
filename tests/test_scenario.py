"""Scenario patch model and runner (spec §12)."""

from decimal import Decimal

import pytest

from ouch.config.profile import build_tax_input
from ouch.errors import UsageError
from ouch.model.money import Money
from ouch.scenario.model import (Scenario, apply_patch, get_path,
                                 resolve_patch_value, set_path)
from ouch.scenario import runner


BASE = {
    "tax_year": 2025,
    "taxpayer": {"filing_status": "single", "state": ""},
    "income": {"wages": {"taxpayer_w2": 100_000},
               "retirement": {"roth_conversion": 0}},
}


def _build(raw):
    return build_tax_input(raw, 2025)


# ----- patch value resolution ----------------------------------------------


def test_absolute_patch():
    out = apply_patch(BASE, {"income.retirement.roth_conversion": 50_000})
    assert get_path(out, "income.retirement.roth_conversion") == 50_000
    # base is untouched (deep copy)
    assert get_path(BASE, "income.retirement.roth_conversion") == 0


def test_relative_amount_patch():
    out = apply_patch(BASE, {"income.wages.taxpayer_w2": "+5000"})
    assert Decimal(get_path(out, "income.wages.taxpayer_w2")) == 105_000
    out = apply_patch(BASE, {"income.wages.taxpayer_w2": "-5000"})
    assert Decimal(get_path(out, "income.wages.taxpayer_w2")) == 95_000


def test_relative_percent_patch():
    out = apply_patch(BASE, {"income.wages.taxpayer_w2": "+10%"})
    assert Decimal(get_path(out, "income.wages.taxpayer_w2")) == 110_000


def test_computed_patch():
    out = apply_patch(
        BASE, {"income.retirement.roth_conversion":
               "= income.wages.taxpayer_w2 * 0.10 + 1000"})
    assert Decimal(get_path(out, "income.retirement.roth_conversion")) == 11_000


def test_computed_patch_parens_and_division():
    assert resolve_patch_value(
        BASE, "x", "= (income.wages.taxpayer_w2 + 20000) / 4") == "30000"


def test_computed_patch_unknown_path_fails():
    with pytest.raises(UsageError):
        resolve_patch_value(BASE, "x", "= income.nope.missing * 2")


def test_computed_patch_no_eval_tricks():
    with pytest.raises(UsageError):
        resolve_patch_value(BASE, "x", "= __import__('os').system('true')")


def test_plain_string_patch_passes_through():
    out = apply_patch(BASE, {"taxpayer.state": "NY"})
    assert get_path(out, "taxpayer.state") == "NY"


# ----- runner ---------------------------------------------------------------


def test_run_scenario_and_marginal_cost(data_federal_only):
    baseline = runner.run_scenario(
        BASE, Scenario(name="baseline", patch={}), data_federal_only, _build,
        compute_marginals=False)
    roth = runner.run_scenario(
        BASE, Scenario(name="roth",
                       patch={"income.retirement.roth_conversion": 20_000}),
        data_federal_only, _build, compute_marginals=False)
    assert roth.patch_delta == Money(20_000)
    dtax = (roth.result.total_tax_all_jurisdictions
            - baseline.result.total_tax_all_jurisdictions)
    assert dtax > Money(0)
    cost = runner.marginal_cost(baseline.result, roth)
    # 100k wages → the 20k conversion spans the 22%/24% boundary
    assert Decimal("0.20") < cost < Decimal("0.30")
    assert cost == dtax.ratio(Money(20_000)).quantize(Decimal("0.0001"))


def test_assertions(data_federal_only):
    from ouch.scenario.model import Assertion
    scenario = Scenario(
        name="guarded", patch={"income.retirement.roth_conversion": 500_000},
        assertions=(Assertion(path="result.marginal_rate_federal",
                              op="lt", value=Decimal("0.30")),))
    run = runner.run_scenario(BASE, scenario, data_federal_only, _build)
    assert run.assertion_failures  # 600k of income blows past 30% marginal


def test_result_metric_paths(data_federal_only):
    run = runner.run_scenario(BASE, Scenario(name="b", patch={}),
                              data_federal_only, _build,
                              compute_marginals=False)
    assert runner.result_metric(run.result, "total_tax_all_jurisdictions") > 0
    assert runner.result_metric(
        run.result, "result.total_tax_all_jurisdictions") > 0
    with pytest.raises(UsageError):
        runner.result_metric(run.result, "no.such.metric")


def test_sweep_finds_bracket_cliff(data_federal_only):
    """Sweeping wages across the 22→24 bracket boundary at 103,350 taxable
    (118,350 wages) must flag a cliff at the crossing step."""
    points = runner.sweep(
        BASE, "income.wages.taxpayer_w2",
        Decimal(100_000), Decimal(140_000), Decimal(10_000),
        ["total_tax_all_jurisdictions"], data_federal_only, _build,
        cliff_threshold=Decimal("0.01"))
    assert len(points) == 5
    assert points[0].step_marginal is None
    cliff_values = [p.value for p in points if p.cliff]
    # The 110k→120k step blends 22%/24% (boundary at 118,350 wages), so the
    # full jump registers on the first all-24% step:
    assert cliff_values == [Decimal(130_000)]


def test_sweep_rejects_bad_range(data_federal_only):
    with pytest.raises(UsageError):
        runner.sweep(BASE, "income.wages.taxpayer_w2",
                     Decimal(10), Decimal(0), Decimal(1), [],
                     data_federal_only, _build)


# ----- issue #6: jurisdiction-changing patches reload tax data ---------------

from ouch.cli.common import data_resolver, load_data  # noqa: E402
from ouch.engine import pipeline  # noqa: E402

NY_BASE = {
    "tax_year": 2025,
    "taxpayer": {"filing_status": "single", "state": "NY"},
    "income": {"wages": {"taxpayer_w2": 150_000}},
}


def test_state_patch_loads_the_new_states_data():
    """NY → TX must apply Texas's (zero) income tax, not New York's brackets
    relabelled as TX."""
    resolve = data_resolver()
    base = runner.run_scenario(NY_BASE, Scenario(name="b", patch={}),
                               resolve, _build)
    moved = runner.run_scenario(
        NY_BASE, Scenario(name="tx", patch={"taxpayer.state": "TX"}),
        resolve, _build)
    assert base.result.state.code == "NY" and base.result.state.tax > 0
    assert moved.result.state.code == "TX"
    assert moved.result.state.tax == Money(0)
    assert (moved.result.total_tax_all_jurisdictions
            == base.result.federal_total_tax)


def test_resolver_matches_load_data_and_caches():
    resolve = data_resolver()
    inp = _build(NY_BASE)
    first = resolve(inp)
    assert first == load_data(inp)
    assert resolve(_build(NY_BASE)) is first          # cached by jurisdiction
    tx = _build(apply_patch(NY_BASE, {"taxpayer.state": "TX"}))
    assert resolve(tx).state.meta.jurisdiction == "TX"


def test_sweep_resolves_data_per_point():
    """Sweeping residency_months from 12 down to 6 must start loading the
    former state's data; reusing the 12-month base data would silently drop
    the former state's tax."""
    base = dict(NY_BASE, taxpayer={"filing_status": "single", "state": "NY",
                                   "former_state": "CA",
                                   "residency_months": 12})
    points = runner.sweep(base, "taxpayer.residency_months", Decimal(6),
                          Decimal(12), Decimal(6),
                          ["total_tax_all_jurisdictions"], data_resolver(),
                          _build)
    six = _build(apply_patch(base, {"taxpayer.residency_months": "6"}))
    direct = pipeline.run(six, load_data(six), compute_marginals=False)
    assert direct.other_state is not None and direct.other_state.tax > 0
    assert points[0].total_tax == (direct.total_tax_all_jurisdictions
                                   .round_cent().amount)


# ----- issue #8: templates are complete ---------------------------------------


def test_templates_parse_and_descriptions_are_complete():
    import tomllib
    from ouch.scenario.templates import TEMPLATES
    for name, template in TEMPLATES.items():
        doc = tomllib.loads(template.format(name="x", base="default"))
        assert doc["description"], name
        # A description wrapped onto a TOML comment line is silently cut.
        assert not doc["description"].rstrip().endswith(","), name
        assert doc["tags"], name
    relocate = tomllib.loads(TEMPLATES["relocate-state"].format(
        name="x", base="default"))
    assert "sales, insurance and cost of living" in relocate["description"]
