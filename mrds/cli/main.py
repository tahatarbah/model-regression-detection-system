"""Typer CLI for MRDS."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import typer
import uvicorn
from rich.console import Console
from rich.table import Table

from mrds.core.compare import CompareEngine
from mrds.core.gate import GatePolicy
from mrds.core.runner import EvalRunner, parse_model_override
from mrds.core.schema import AdapterType, MetricConfig, MetricDirection, ModelSpec, ThresholdConfig, load_suite
from mrds.storage import Store, default_db_path

app = typer.Typer(
    name="mrds",
    help="Model Regression Detection System",
    no_args_is_help=True,
)
console = Console()


def _store(db: Optional[Path]) -> Store:
    return Store(db or default_db_path())


def _merge_model(suite_model: ModelSpec | None, override: str | None) -> ModelSpec:
    if override is None:
        if suite_model is None:
            raise typer.BadParameter("Provide --model or set model in suite YAML")
        return suite_model
    parsed = parse_model_override(
        override,
        adapter=suite_model.adapter if suite_model else None,
    )
    if suite_model is None:
        return parsed
    data = suite_model.model_dump()
    if parsed.adapter == AdapterType.LLM:
        data["adapter"] = AdapterType.LLM.value
        if parsed.model:
            data["model"] = parsed.model
        if parsed.mock_responses:
            data["mock_responses"] = parsed.mock_responses
    else:
        data["adapter"] = AdapterType.CLASSICAL.value
        if parsed.path:
            data["path"] = parsed.path
    return ModelSpec.model_validate(data)


@app.command()
def run(
    suite: Path = typer.Option(..., "--suite", "-s", help="Path to suite YAML"),
    model: Optional[str] = typer.Option(
        None, "--model", "-m", help="Model path, module:callable, or llm:name"
    ),
    tag: Optional[str] = typer.Option(None, "--tag", "-t", help="Tag this run (e.g. prod)"),
    label: str = typer.Option("model", "--label", "-l", help="Model label for display"),
    db: Optional[Path] = typer.Option(None, "--db", help="SQLite DB path"),
) -> None:
    """Run an eval suite and store results."""
    store = _store(db)
    cfg = load_suite(suite)
    model_spec = _merge_model(cfg.model, model)
    runner = EvalRunner(store)
    result = runner.run(
        cfg,
        model=model_spec,
        model_label=label,
        tag=tag.lstrip("@") if tag else None,
        suite_path=str(suite.resolve()),
    )
    console.print(f"[green]Run saved[/green] id={result.run_id} suite={result.suite_name}")
    table = Table(title="Metrics")
    table.add_column("Metric")
    table.add_column("Value")
    for k, v in result.metrics.items():
        table.add_row(k, f"{v:.6f}")
    console.print(table)


@app.command()
def compare(
    baseline: str = typer.Option(..., "--baseline", "-b", help="Run id or @tag"),
    candidate: str = typer.Option(..., "--candidate", "-c", help="Run id or @tag"),
    suite_name: Optional[str] = typer.Option(
        None, "--suite-name", help="Suite name (required for @tag refs)"
    ),
    db: Optional[Path] = typer.Option(None, "--db"),
) -> None:
    """Compare two runs and show metric deltas."""
    store = _store(db)
    b = store.resolve_run_ref(baseline, suite_name)
    c = store.resolve_run_ref(candidate, suite_name)
    if b is None:
        console.print(f"[red]Baseline not found:[/red] {baseline}")
        raise typer.Exit(1)
    if c is None:
        console.print(f"[red]Candidate not found:[/red] {candidate}")
        raise typer.Exit(1)
    if b["suite_name"] != c["suite_name"]:
        console.print("[red]Runs belong to different suites[/red]")
        raise typer.Exit(1)

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

    table = Table(title=f"Compare {b['suite_name']}")
    table.add_column("Metric")
    table.add_column("Baseline")
    table.add_column("Candidate")
    table.add_column("Delta")
    table.add_column("Status")
    for d in result.metric_deltas:
        status = "[red]BREACH[/red]" if d.breached else "[green]OK[/green]"
        table.add_row(
            d.name,
            f"{d.baseline:.6f}",
            f"{d.candidate:.6f}",
            f"{d.delta:.6f}",
            status,
        )
    console.print(table)
    regressed = [e for e in result.example_diffs if e.regressed]
    console.print(f"Regressed examples: {len(regressed)}")
    if not result.passed:
        raise typer.Exit(1)


@app.command()
def gate(
    suite: Path = typer.Option(..., "--suite", "-s"),
    baseline: str = typer.Option(..., "--baseline", "-b", help="Run id or @tag"),
    candidate: Optional[str] = typer.Option(
        None, "--candidate", "-c", help="Existing run id/@tag, or omit to run --model"
    ),
    model: Optional[str] = typer.Option(
        None, "--model", "-m", help="Candidate model if running fresh"
    ),
    label: str = typer.Option("candidate", "--label"),
    db: Optional[Path] = typer.Option(None, "--db"),
) -> None:
    """Run (optional) candidate, compare to baseline, exit non-zero on regression."""
    store = _store(db)
    cfg = load_suite(suite)
    b = store.resolve_run_ref(baseline, cfg.name)
    if b is None:
        console.print(f"[red]Baseline not found:[/red] {baseline}")
        raise typer.Exit(1)

    if candidate:
        c = store.resolve_run_ref(candidate, cfg.name)
        if c is None:
            console.print(f"[red]Candidate not found:[/red] {candidate}")
            raise typer.Exit(1)
        cand_id = c["id"]
        cand_metrics = c["metrics"]
        cand_examples = c.get("examples", [])
    else:
        model_spec = _merge_model(cfg.model, model)
        runner = EvalRunner(store)
        result = runner.run(
            cfg,
            model=model_spec,
            model_label=label,
            tag=None,
            suite_path=str(suite.resolve()),
        )
        cand_id = result.run_id
        cand_metrics = result.metrics
        c_full = store.get_run(cand_id)
        cand_examples = (c_full or {}).get("examples", [])

    engine = CompareEngine()
    comparison = engine.compare_metrics(
        baseline_metrics=b["metrics"],
        candidate_metrics=cand_metrics,
        metric_configs=cfg.metrics,
        baseline_run_id=b["id"],
        candidate_run_id=cand_id,
        suite_name=cfg.name,
    )
    engine.attach_example_diffs(comparison, b.get("examples", []), cand_examples)
    gate_result = GatePolicy().evaluate(comparison)
    console.print(gate_result.message)
    raise typer.Exit(0 if gate_result.passed else 1)


@app.command("list-runs")
def list_runs(
    suite_name: Optional[str] = typer.Option(None, "--suite-name"),
    db: Optional[Path] = typer.Option(None, "--db"),
    limit: int = typer.Option(20, "--limit"),
) -> None:
    store = _store(db)
    rows = store.list_runs(suite_name=suite_name, limit=limit)
    table = Table(title="Runs")
    table.add_column("ID")
    table.add_column("Suite")
    table.add_column("Label")
    table.add_column("Tag")
    table.add_column("Metrics")
    table.add_column("Created")
    for r in rows:
        table.add_row(
            r["id"][:8],
            r["suite_name"],
            r["model_label"],
            r["tag"] or "",
            json.dumps(r["metrics"]),
            r["created_at"] or "",
        )
    console.print(table)


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(8000, "--port"),
    db: Optional[Path] = typer.Option(None, "--db"),
) -> None:
    """Start API + dashboard."""
    if db:
        import os

        os.environ["MRDS_DB"] = str(Path(db).resolve())
    console.print(f"Serving on http://{host}:{port}")
    uvicorn.run("mrds.api.app:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    app()
