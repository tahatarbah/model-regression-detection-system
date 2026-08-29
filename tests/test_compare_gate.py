"""Unit tests for compare / gate logic."""

from mrds.core.compare import CompareEngine
from mrds.core.gate import GatePolicy
from mrds.core.schema import MetricConfig, MetricDirection, ThresholdConfig


def test_higher_is_better_absolute_breach():
    engine = CompareEngine()
    result = engine.compare_metrics(
        baseline_metrics={"accuracy": 0.95},
        candidate_metrics={"accuracy": 0.80},
        metric_configs=[
            MetricConfig(
                name="accuracy",
                direction=MetricDirection.HIGHER_IS_BETTER,
                threshold=ThresholdConfig(absolute=0.05),
            )
        ],
        baseline_run_id="b",
        candidate_run_id="c",
        suite_name="t",
    )
    assert not result.passed
    assert result.metric_deltas[0].breached


def test_higher_is_better_within_threshold():
    engine = CompareEngine()
    result = engine.compare_metrics(
        baseline_metrics={"accuracy": 0.95},
        candidate_metrics={"accuracy": 0.93},
        metric_configs=[
            MetricConfig(
                name="accuracy",
                direction=MetricDirection.HIGHER_IS_BETTER,
                threshold=ThresholdConfig(absolute=0.05),
            )
        ],
        baseline_run_id="b",
        candidate_run_id="c",
        suite_name="t",
    )
    assert result.passed
    assert not result.metric_deltas[0].breached


def test_lower_is_better_breach():
    engine = CompareEngine()
    result = engine.compare_metrics(
        baseline_metrics={"mae": 0.1},
        candidate_metrics={"mae": 0.5},
        metric_configs=[
            MetricConfig(
                name="mae",
                direction=MetricDirection.LOWER_IS_BETTER,
                threshold=ThresholdConfig(absolute=0.1),
            )
        ],
        baseline_run_id="b",
        candidate_run_id="c",
        suite_name="t",
    )
    assert not result.passed


def test_relative_threshold():
    engine = CompareEngine()
    result = engine.compare_metrics(
        baseline_metrics={"f1": 1.0},
        candidate_metrics={"f1": 0.7},
        metric_configs=[
            MetricConfig(
                name="f1",
                direction=MetricDirection.HIGHER_IS_BETTER,
                threshold=ThresholdConfig(relative=0.2),
            )
        ],
        baseline_run_id="b",
        candidate_run_id="c",
        suite_name="t",
    )
    assert not result.passed


def test_gate_policy_messages():
    engine = CompareEngine()
    comparison = engine.compare_metrics(
        baseline_metrics={"accuracy": 1.0},
        candidate_metrics={"accuracy": 0.5},
        metric_configs=[
            MetricConfig(
                name="accuracy",
                direction=MetricDirection.HIGHER_IS_BETTER,
                threshold=ThresholdConfig(absolute=0.01),
            )
        ],
        baseline_run_id="b",
        candidate_run_id="c",
        suite_name="demo",
    )
    gate = GatePolicy().evaluate(comparison)
    assert not gate.passed
    assert "GATE FAIL" in gate.message
