"""FastAPI application for MRDS dashboard backend."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from mrds.core.compare import CompareEngine
from mrds.core.schema import MetricConfig, MetricDirection, ThresholdConfig, load_suite
from mrds.storage import Store

_store: Store | None = None

app = FastAPI(title="MRDS", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class CompareRequest(BaseModel):
    baseline: str
    candidate: str
    suite_name: str | None = None


def get_store() -> Store:
    global _store
    if _store is None:
        _store = Store()
    return _store


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/runs")
def list_runs(suite_name: str | None = None, limit: int = 100) -> list[dict]:
    return get_store().list_runs(suite_name=suite_name, limit=limit)


@app.get("/api/runs/{run_id}")
def get_run(run_id: str) -> dict:
    run = get_store().get_run(run_id)
    if run is None:
        raise HTTPException(404, "Run not found")
    return run


@app.get("/api/suites")
def list_suites() -> list[dict]:
    return get_store().list_suites()


@app.post("/api/compare")
def compare(body: CompareRequest) -> dict[str, Any]:
    store = get_store()
    b = store.resolve_run_ref(body.baseline, body.suite_name)
    c = store.resolve_run_ref(body.candidate, body.suite_name)
    if b is None:
        raise HTTPException(404, f"Baseline not found: {body.baseline}")
    if c is None:
        raise HTTPException(404, f"Candidate not found: {body.candidate}")
    if b["suite_name"] != c["suite_name"]:
        raise HTTPException(400, "Runs belong to different suites")

    suite_cfg = None
    if b.get("suite_path"):
        try:
            suite_cfg = load_suite(b["suite_path"])
        except Exception:
            suite_cfg = None

    if suite_cfg:
        metric_configs = suite_cfg.metrics
    else:
        metric_configs = [
            MetricConfig(
                name=k,
                direction=MetricDirection.LOWER_IS_BETTER
                if k in {"mae", "rmse", "mse", "latency_ms", "tokens"}
                else MetricDirection.HIGHER_IS_BETTER,
                threshold=ThresholdConfig(),
            )
            for k in b["metrics"]
        ]

    engine = CompareEngine()
    result = engine.compare_metrics(
        baseline_metrics=b["metrics"],
        candidate_metrics=c["metrics"],
        metric_configs=metric_configs,
        baseline_run_id=b["id"],
        candidate_run_id=c["id"],
        suite_name=b["suite_name"],
    )
    engine.attach_example_diffs(result, b.get("examples", []), c.get("examples", []))
    return {
        "baseline_run_id": result.baseline_run_id,
        "candidate_run_id": result.candidate_run_id,
        "suite_name": result.suite_name,
        "passed": result.passed,
        "metric_deltas": [
            {
                "name": d.name,
                "baseline": d.baseline,
                "candidate": d.candidate,
                "delta": d.delta,
                "relative_delta": d.relative_delta,
                "direction": d.direction.value,
                "breached": d.breached,
                "reason": d.reason,
            }
            for d in result.metric_deltas
        ],
        "example_diffs": [
            {
                "example_id": e.example_id,
                "baseline_output": e.baseline_output,
                "candidate_output": e.candidate_output,
                "baseline_score": e.baseline_score,
                "candidate_score": e.candidate_score,
                "baseline_passed": e.baseline_passed,
                "candidate_passed": e.candidate_passed,
                "regressed": e.regressed,
            }
            for e in result.example_diffs
        ],
    }


def _mount_static() -> None:
    dist = Path(__file__).resolve().parents[2] / "web" / "dist"
    if not dist.is_dir():
        return
    assets = dist / "assets"
    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(dist / "index.html")

    @app.get("/{full_path:path}")
    def spa(full_path: str) -> FileResponse:
        if full_path.startswith("api/"):
            raise HTTPException(404)
        candidate = dist / full_path
        if candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(dist / "index.html")


_mount_static()
