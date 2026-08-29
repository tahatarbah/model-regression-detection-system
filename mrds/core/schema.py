"""Eval suite schema and shared data types."""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, field_validator


class TaskType(str, Enum):
    CLASSIFICATION = "classification"
    REGRESSION = "regression"
    LLM = "llm"


class MetricDirection(str, Enum):
    HIGHER_IS_BETTER = "higher_is_better"
    LOWER_IS_BETTER = "lower_is_better"


class AdapterType(str, Enum):
    CLASSICAL = "classical"
    LLM = "llm"


class ThresholdConfig(BaseModel):
    """Fail if absolute or relative degradation crosses these bounds."""

    absolute: float | None = None
    relative: float | None = None


class MetricConfig(BaseModel):
    name: str
    direction: MetricDirection = MetricDirection.HIGHER_IS_BETTER
    threshold: ThresholdConfig = Field(default_factory=ThresholdConfig)


class ModelSpec(BaseModel):
    """How to load / call a model for an eval run."""

    adapter: AdapterType
    # classical: path to joblib/pickle or "module:callable"
    path: str | None = None
    # llm
    model: str | None = None
    prompt_template: str | None = None
    system_prompt: str | None = None
    temperature: float = 0.0
    max_tokens: int = 256
    base_url: str | None = None
    api_key_env: str = "OPENAI_API_KEY"
    # mock for offline / tests
    mock_responses: dict[str, str] | None = None


class DatasetConfig(BaseModel):
    path: str
    # classical columns
    feature_columns: list[str] | None = None
    label_column: str | None = None
    # llm fields in JSONL
    input_field: str = "input"
    expected_field: str = "expected"
    id_field: str = "id"


class ScorerConfig(BaseModel):
    """LLM example scorers. Classical metrics come from MetricConfig names."""

    type: str = "exact_match"  # exact_match | contains | regex | llm_judge
    pattern: str | None = None
    judge_model: str | None = None
    judge_rubric: str | None = None


class SuiteConfig(BaseModel):
    name: str
    description: str = ""
    task_type: TaskType
    dataset: DatasetConfig
    metrics: list[MetricConfig]
    model: ModelSpec | None = None
    scorer: ScorerConfig | None = None
    # Resolved at load time
    suite_dir: Path | None = Field(default=None, exclude=True)

    @field_validator("metrics")
    @classmethod
    def at_least_one_metric(cls, v: list[MetricConfig]) -> list[MetricConfig]:
        if not v:
            raise ValueError("suite must define at least one metric")
        return v


class Example(BaseModel):
    id: str
    input: Any
    expected: Any = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class Prediction(BaseModel):
    example_id: str
    output: Any
    latency_ms: float | None = None
    tokens_in: int | None = None
    tokens_out: int | None = None
    score: float | None = None
    passed: bool | None = None
    details: dict[str, Any] = Field(default_factory=dict)


def load_suite(path: str | Path) -> SuiteConfig:
    path = Path(path).resolve()
    with path.open(encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    if not isinstance(raw, dict):
        raise ValueError(f"Suite file must be a mapping: {path}")
    suite = SuiteConfig.model_validate(raw)
    suite.suite_dir = path.parent
    return suite


def resolve_dataset_path(suite: SuiteConfig) -> Path:
    assert suite.suite_dir is not None
    p = Path(suite.dataset.path)
    if p.is_absolute():
        return p
    return (suite.suite_dir / p).resolve()
