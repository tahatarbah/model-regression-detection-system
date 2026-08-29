"""Classical adapter integration tests."""

from pathlib import Path

import pytest

from mrds.core.runner import EvalRunner
from mrds.core.schema import load_suite
from mrds.storage import Store

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples"


@pytest.fixture(scope="module")
def trained_models():
    from examples.models import train_and_save

    return train_and_save(EXAMPLES)


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / "test.db")


def test_classical_run_and_gate(trained_models, store, monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT))
    suite = load_suite(EXAMPLES / "iris_classification.yaml")
    runner = EvalRunner(store)

    baseline = runner.run(
        suite,
        model_label="good",
        tag="prod",
        suite_path=str(EXAMPLES / "iris_classification.yaml"),
    )
    assert baseline.metrics["accuracy"] > 0.8

    from mrds.core.schema import AdapterType, ModelSpec

    bad = runner.run(
        suite,
        model=ModelSpec(adapter=AdapterType.CLASSICAL, path=str(trained_models[1])),
        model_label="bad",
        suite_path=str(EXAMPLES / "iris_classification.yaml"),
    )
    assert bad.metrics["accuracy"] < baseline.metrics["accuracy"]

    from mrds.core.compare import CompareEngine
    from mrds.core.gate import GatePolicy

    b = store.get_run(baseline.run_id)
    c = store.get_run(bad.run_id)
    comparison = CompareEngine().compare_metrics(
        baseline_metrics=b["metrics"],
        candidate_metrics=c["metrics"],
        metric_configs=suite.metrics,
        baseline_run_id=b["id"],
        candidate_run_id=c["id"],
        suite_name=suite.name,
    )
    gate = GatePolicy().evaluate(comparison)
    assert not gate.passed
