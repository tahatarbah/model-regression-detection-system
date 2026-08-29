"""LLM adapter tests with mock responses (no network)."""

from pathlib import Path

from mrds.adapters.llm import LLMAdapter, LLMClient, score_prediction
from mrds.core.runner import EvalRunner
from mrds.core.schema import Example, ModelSpec, AdapterType, Prediction, ScorerConfig, load_suite
from mrds.storage import Store

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples"


def test_exact_match_scorer():
    ex = Example(id="1", input="hi", expected="Paris")
    pred = Prediction(example_id="1", output="paris")
    scored = score_prediction(ex, pred, ScorerConfig(type="exact_match"))
    assert scored.passed and scored.score == 1.0


def test_contains_scorer():
    ex = Example(id="1", input="hi", expected="Paris")
    pred = Prediction(example_id="1", output="The capital is Paris.")
    scored = score_prediction(ex, pred, ScorerConfig(type="contains"))
    assert scored.passed


def test_mock_llm_client():
    client = LLMClient(api_key=None, mock_responses={"France": "Paris", "*": "x"})
    out = client.chat(
        model="mock",
        messages=[{"role": "user", "content": "capital of France?"}],
    )
    assert out["content"] == "Paris"


def test_llm_suite_good_vs_bad(tmp_path):
    store = Store(tmp_path / "llm.db")
    runner = EvalRunner(store)
    good_suite = load_suite(EXAMPLES / "llm_qa.yaml")
    bad_suite = load_suite(EXAMPLES / "llm_qa_bad.yaml")

    good = runner.run(
        good_suite,
        model_label="good",
        tag="prod",
        suite_path=str(EXAMPLES / "llm_qa.yaml"),
    )
    bad = runner.run(
        bad_suite,
        model_label="bad",
        suite_path=str(EXAMPLES / "llm_qa_bad.yaml"),
    )
    assert good.metrics["exact_match"] == 1.0
    assert bad.metrics["exact_match"] == 0.0

    from mrds.core.compare import CompareEngine
    from mrds.core.gate import GatePolicy

    b = store.get_run(good.run_id)
    c = store.get_run(bad.run_id)
    # Use good suite thresholds; both share same suite name? bad suite has different name.
    # Force compare with good suite metrics config and rename for test:
    comparison = CompareEngine().compare_metrics(
        baseline_metrics=b["metrics"],
        candidate_metrics=c["metrics"],
        metric_configs=good_suite.metrics,
        baseline_run_id=b["id"],
        candidate_run_id=c["id"],
        suite_name="llm_qa",
    )
    gate = GatePolicy().evaluate(comparison)
    assert not gate.passed


def test_llm_adapter_batch():
    spec = ModelSpec(
        adapter=AdapterType.LLM,
        model="mock",
        prompt_template="{input}",
        mock_responses={"*": "Paris"},
    )
    adapter = LLMAdapter(spec)
    preds = adapter.predict_batch([Example(id="1", input="capital of France?", expected="Paris")])
    assert preds[0].output == "Paris"
