"""Classical ML adapter and metrics."""

from __future__ import annotations

import importlib
import time
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import (
    accuracy_score,
    f1_score,
    mean_absolute_error,
    mean_squared_error,
)

from mrds.core.schema import (
    Example,
    ModelSpec,
    Prediction,
    SuiteConfig,
    TaskType,
    resolve_dataset_path,
)


def _is_module_callable(path: str) -> bool:
    """True for 'pkg.mod:attr', false for filesystem paths (incl. Windows drives)."""
    if "/" in path or "\\" in path:
        return False
    if path.count(":") != 1:
        return False
    return not Path(path).exists()


def _load_callable(path: str) -> Any:
    if _is_module_callable(path):
        module_name, attr = path.split(":", 1)
        mod = importlib.import_module(module_name)
        return getattr(mod, attr)
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Model path not found: {path}")
    return joblib.load(p)


class ClassicalAdapter:
    def __init__(self, model: Any):
        self.model = model

    @classmethod
    def from_spec(cls, spec: ModelSpec, *, base_dir: Path | None = None) -> ClassicalAdapter:
        if not spec.path:
            raise ValueError("classical model requires path")
        path = spec.path
        if not _is_module_callable(path):
            p = Path(path)
            if not p.is_absolute() and base_dir is not None:
                path = str((base_dir / p).resolve())
        return cls(_load_callable(path))

    def predict_batch(self, examples: list[Example]) -> list[Prediction]:
        if not examples:
            return []
        # inputs are feature vectors / dicts
        rows = []
        for ex in examples:
            if isinstance(ex.input, dict):
                rows.append(ex.input)
            elif isinstance(ex.input, (list, tuple)):
                rows.append({str(i): v for i, v in enumerate(ex.input)})
            else:
                rows.append({"x": ex.input})
        df = pd.DataFrame(rows)
        t0 = time.perf_counter()
        preds = self.model.predict(df)
        latency = (time.perf_counter() - t0) * 1000.0
        per = latency / max(len(examples), 1)
        out: list[Prediction] = []
        for ex, pred in zip(examples, preds):
            val = pred.item() if hasattr(pred, "item") else pred
            out.append(
                Prediction(
                    example_id=ex.id,
                    output=val,
                    latency_ms=per,
                )
            )
        return out


def load_classical_examples(suite: SuiteConfig) -> list[Example]:
    path = resolve_dataset_path(suite)
    df = pd.read_csv(path)
    feats = suite.dataset.feature_columns
    label = suite.dataset.label_column
    if not feats or not label:
        raise ValueError("classical suite requires feature_columns and label_column")
    examples: list[Example] = []
    for i, row in df.iterrows():
        examples.append(
            Example(
                id=str(row.get("id", i)),
                input={c: row[c] for c in feats},
                expected=row[label],
            )
        )
    return examples


def compute_classical_metrics(
    examples: list[Example],
    predictions: list[Prediction],
    suite: SuiteConfig,
) -> tuple[dict[str, float], list[Prediction]]:
    by_id = {p.example_id: p for p in predictions}
    y_true = []
    y_pred = []
    scored: list[Prediction] = []
    for ex in examples:
        p = by_id[ex.id]
        y_true.append(ex.expected)
        y_pred.append(p.output)
        correct = p.output == ex.expected
        scored.append(
            p.model_copy(
                update={
                    "score": 1.0 if correct else 0.0,
                    "passed": bool(correct)
                    if suite.task_type == TaskType.CLASSIFICATION
                    else None,
                }
            )
        )

    yt = np.array(y_true)
    yp = np.array(y_pred)
    metrics: dict[str, float] = {}
    wanted = {m.name for m in suite.metrics}

    if suite.task_type == TaskType.CLASSIFICATION:
        if "accuracy" in wanted:
            metrics["accuracy"] = float(accuracy_score(yt, yp))
        if "f1" in wanted or "f1_macro" in wanted:
            key = "f1" if "f1" in wanted else "f1_macro"
            metrics[key] = float(f1_score(yt, yp, average="macro", zero_division=0))
        if "f1_weighted" in wanted:
            metrics["f1_weighted"] = float(
                f1_score(yt, yp, average="weighted", zero_division=0)
            )
    elif suite.task_type == TaskType.REGRESSION:
        if "mae" in wanted:
            metrics["mae"] = float(mean_absolute_error(yt, yp))
        if "rmse" in wanted:
            metrics["rmse"] = float(np.sqrt(mean_squared_error(yt, yp)))
        if "mse" in wanted:
            metrics["mse"] = float(mean_squared_error(yt, yp))

    # always record mean latency if present
    latencies = [p.latency_ms for p in predictions if p.latency_ms is not None]
    if latencies and "latency_ms" in wanted:
        metrics["latency_ms"] = float(np.mean(latencies))

    return metrics, scored
