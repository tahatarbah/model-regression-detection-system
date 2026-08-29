"""Eval runner — load suite, adapt model, score, persist."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from mrds.adapters.classical import (
    ClassicalAdapter,
    compute_classical_metrics,
    load_classical_examples,
)
from mrds.adapters.llm import LLMAdapter, compute_llm_metrics, load_llm_examples
from mrds.core.schema import (
    AdapterType,
    ModelSpec,
    Prediction,
    SuiteConfig,
    TaskType,
    load_suite,
)
from mrds.storage import Store


@dataclass
class RunResult:
    run_id: str
    suite_name: str
    model_label: str
    tag: str | None
    metrics: dict[str, float]
    predictions: list[Prediction] = field(default_factory=list)


class EvalRunner:
    def __init__(self, store: Store | None = None):
        self.store = store or Store()

    def run(
        self,
        suite: SuiteConfig | str | Path,
        *,
        model: ModelSpec | None = None,
        model_label: str = "model",
        tag: str | None = None,
        suite_path: str | None = None,
    ) -> RunResult:
        if not isinstance(suite, SuiteConfig):
            path = Path(suite)
            suite_path = str(path.resolve())
            suite = load_suite(path)

        model_spec = model or suite.model
        if model_spec is None:
            raise ValueError("No model specified on suite or via --model")

        self.store.register_suite(
            name=suite.name,
            path=suite_path or "",
            description=suite.description,
            task_type=suite.task_type.value,
            config=suite.model_dump(mode="json", exclude={"suite_dir"}),
        )

        if suite.task_type in (TaskType.CLASSIFICATION, TaskType.REGRESSION):
            examples = load_classical_examples(suite)
            adapter = ClassicalAdapter.from_spec(model_spec, base_dir=suite.suite_dir)
            predictions = adapter.predict_batch(examples)
            metrics, scored = compute_classical_metrics(examples, predictions, suite)
        elif suite.task_type == TaskType.LLM:
            examples = load_llm_examples(suite)
            adapter = LLMAdapter(model_spec)
            predictions = adapter.predict_batch(examples)
            metrics, scored = compute_llm_metrics(
                examples, predictions, suite, client=adapter.client
            )
        else:
            raise ValueError(f"Unsupported task_type: {suite.task_type}")

        example_rows: list[dict[str, Any]] = []
        by_id_ex = {e.id: e for e in examples}
        for p in scored:
            ex = by_id_ex[p.example_id]
            example_rows.append(
                {
                    "example_id": p.example_id,
                    "input": ex.input,
                    "expected": ex.expected,
                    "output": p.output,
                    "score": p.score,
                    "passed": p.passed,
                    "latency_ms": p.latency_ms,
                    "tokens_in": p.tokens_in,
                    "tokens_out": p.tokens_out,
                    "details": p.details,
                }
            )

        run_id = self.store.save_run(
            suite_name=suite.name,
            suite_path=suite_path,
            model_label=model_label,
            tag=tag,
            task_type=suite.task_type.value,
            metrics=metrics,
            examples=example_rows,
        )
        return RunResult(
            run_id=run_id,
            suite_name=suite.name,
            model_label=model_label,
            tag=tag,
            metrics=metrics,
            predictions=scored,
        )


def parse_model_override(raw: str, adapter: AdapterType | None = None) -> ModelSpec:
    """
    Parse CLI model string.
    - classical path: path/to/model.joblib
    - classical callable: examples.models:good_clf
    - llm: llm:gpt-4o-mini
    - mock llm: mock:good  (uses built-in mock map from suite if present)
    """
    if raw.startswith("llm:"):
        return ModelSpec(adapter=AdapterType.LLM, model=raw[4:])
    if raw.startswith("mock:"):
        # placeholder; suite mock_responses usually preferred
        return ModelSpec(
            adapter=AdapterType.LLM,
            model="mock",
            mock_responses={"*": raw[5:]},
        )
    return ModelSpec(adapter=adapter or AdapterType.CLASSICAL, path=raw)
