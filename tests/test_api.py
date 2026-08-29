"""API smoke tests."""

from pathlib import Path

from fastapi.testclient import TestClient

from mrds.api import app as app_module
from mrds.core.runner import EvalRunner
from mrds.core.schema import load_suite
from mrds.storage import Store

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples"


def test_api_runs_and_compare(tmp_path, monkeypatch):
    db = tmp_path / "api.db"
    store = Store(db)
    app_module._store = store

    from examples.models import train_and_save

    train_and_save(EXAMPLES)
    suite = load_suite(EXAMPLES / "iris_classification.yaml")
    runner = EvalRunner(store)
    b = runner.run(suite, model_label="good", tag="prod", suite_path=str(EXAMPLES / "iris_classification.yaml"))
    from mrds.core.schema import AdapterType, ModelSpec

    c = runner.run(
        suite,
        model=ModelSpec(adapter=AdapterType.CLASSICAL, path=str(EXAMPLES / "iris_bad.joblib")),
        model_label="bad",
        suite_path=str(EXAMPLES / "iris_classification.yaml"),
    )

    client = TestClient(app_module.app)
    assert client.get("/api/health").json()["status"] == "ok"
    runs = client.get("/api/runs").json()
    assert len(runs) >= 2
    detail = client.get(f"/api/runs/{b.run_id}").json()
    assert detail["id"] == b.run_id
    assert "examples" in detail
    suites = client.get("/api/suites").json()
    assert any(s["name"] == "iris_classification" for s in suites)
    cmp = client.post(
        "/api/compare",
        json={"baseline": b.run_id, "candidate": c.run_id},
    ).json()
    assert cmp["passed"] is False
    assert any(d["breached"] for d in cmp["metric_deltas"])
