"""LLM adapter, OpenAI-compatible client, and scorers."""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Any

import httpx

from mrds.core.schema import (
    Example,
    ModelSpec,
    Prediction,
    ScorerConfig,
    SuiteConfig,
    resolve_dataset_path,
)


class LLMClient:
    def __init__(
        self,
        *,
        api_key: str | None,
        base_url: str = "https://api.openai.com/v1",
        mock_responses: dict[str, str] | None = None,
    ):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.mock_responses = mock_responses or {}

    def chat(
        self,
        *,
        model: str,
        messages: list[dict[str, str]],
        temperature: float = 0.0,
        max_tokens: int = 256,
    ) -> dict[str, Any]:
        # Offline mock: match last user message content
        user_content = ""
        for m in reversed(messages):
            if m.get("role") == "user":
                user_content = m.get("content", "")
                break
        if self.mock_responses:
            for key, val in self.mock_responses.items():
                if key in user_content or key == "*":
                    return {
                        "content": val,
                        "tokens_in": 0,
                        "tokens_out": 0,
                        "latency_ms": 0.0,
                    }
            # default empty if no match
            return {
                "content": self.mock_responses.get("*", ""),
                "tokens_in": 0,
                "tokens_out": 0,
                "latency_ms": 0.0,
            }

        if not self.api_key:
            raise RuntimeError(
                "No API key and no mock_responses. Set OPENAI_API_KEY or use mock."
            )

        t0 = time.perf_counter()
        with httpx.Client(timeout=60.0) as client:
            resp = client.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "messages": messages,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                },
            )
            resp.raise_for_status()
            data = resp.json()
        latency = (time.perf_counter() - t0) * 1000.0
        choice = data["choices"][0]["message"]["content"]
        usage = data.get("usage") or {}
        return {
            "content": choice,
            "tokens_in": usage.get("prompt_tokens"),
            "tokens_out": usage.get("completion_tokens"),
            "latency_ms": latency,
        }


def render_prompt(template: str, example: Example) -> str:
    ctx: dict[str, Any] = {"input": example.input, "id": example.id}
    if isinstance(example.input, dict):
        ctx.update(example.input)
    elif isinstance(example.input, str):
        ctx["question"] = example.input
        ctx["text"] = example.input
    try:
        return template.format(**ctx)
    except KeyError:
        # fall back: replace {input} only
        return template.replace("{input}", str(example.input))


class LLMAdapter:
    def __init__(self, spec: ModelSpec, client: LLMClient | None = None):
        self.spec = spec
        if client is not None:
            self.client = client
        else:
            api_key = os.environ.get(spec.api_key_env) if spec.api_key_env else None
            base = spec.base_url or os.environ.get(
                "OPENAI_BASE_URL", "https://api.openai.com/v1"
            )
            self.client = LLMClient(
                api_key=api_key,
                base_url=base,
                mock_responses=spec.mock_responses,
            )

    def predict_batch(self, examples: list[Example]) -> list[Prediction]:
        if not self.spec.model and not self.spec.mock_responses:
            raise ValueError("llm model name required")
        template = self.spec.prompt_template or "{input}"
        out: list[Prediction] = []
        for ex in examples:
            user = render_prompt(template, ex)
            messages: list[dict[str, str]] = []
            if self.spec.system_prompt:
                messages.append({"role": "system", "content": self.spec.system_prompt})
            messages.append({"role": "user", "content": user})
            result = self.client.chat(
                model=self.spec.model or "mock",
                messages=messages,
                temperature=self.spec.temperature,
                max_tokens=self.spec.max_tokens,
            )
            out.append(
                Prediction(
                    example_id=ex.id,
                    output=result["content"],
                    latency_ms=result.get("latency_ms"),
                    tokens_in=result.get("tokens_in"),
                    tokens_out=result.get("tokens_out"),
                )
            )
        return out


def load_llm_examples(suite: SuiteConfig) -> list[Example]:
    path = resolve_dataset_path(suite)
    examples: list[Example] = []
    with path.open(encoding="utf-8") as f:
        for i, line in enumerate(f):
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            eid = str(row.get(suite.dataset.id_field, i))
            examples.append(
                Example(
                    id=eid,
                    input=row[suite.dataset.input_field],
                    expected=row.get(suite.dataset.expected_field),
                    metadata={k: v for k, v in row.items() if k not in {
                        suite.dataset.input_field,
                        suite.dataset.expected_field,
                        suite.dataset.id_field,
                    }},
                )
            )
    return examples


def score_prediction(
    example: Example,
    prediction: Prediction,
    scorer: ScorerConfig | None,
    client: LLMClient | None = None,
) -> Prediction:
    scorer = scorer or ScorerConfig(type="exact_match")
    expected = example.expected
    output = prediction.output
    out_s = "" if output is None else str(output).strip()
    exp_s = "" if expected is None else str(expected).strip()

    passed = False
    score = 0.0
    details: dict[str, Any] = {"scorer": scorer.type}

    if scorer.type == "exact_match":
        passed = out_s.lower() == exp_s.lower()
        score = 1.0 if passed else 0.0
    elif scorer.type == "contains":
        passed = exp_s.lower() in out_s.lower()
        score = 1.0 if passed else 0.0
    elif scorer.type == "regex":
        pattern = scorer.pattern or exp_s
        passed = bool(re.search(pattern, out_s, re.IGNORECASE | re.DOTALL))
        score = 1.0 if passed else 0.0
    elif scorer.type == "llm_judge":
        if client is None:
            raise RuntimeError("llm_judge requires an LLM client")
        rubric = scorer.judge_rubric or (
            "Score 1 if the answer is correct given the expected answer, else 0. "
            "Reply with only a number 0 or 1."
        )
        judge_model = scorer.judge_model or "gpt-4o-mini"
        prompt = (
            f"{rubric}\n\nQuestion/Input: {example.input}\n"
            f"Expected: {expected}\nModel answer: {output}\nScore:"
        )
        result = client.chat(
            model=judge_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=8,
        )
        raw = result["content"].strip()
        m = re.search(r"([01](?:\.\d+)?)", raw)
        score = float(m.group(1)) if m else 0.0
        passed = score >= 0.5
        details["judge_raw"] = raw
    else:
        raise ValueError(f"Unknown scorer type: {scorer.type}")

    return prediction.model_copy(
        update={"score": score, "passed": passed, "details": details}
    )


def compute_llm_metrics(
    examples: list[Example],
    predictions: list[Prediction],
    suite: SuiteConfig,
    client: LLMClient | None = None,
) -> tuple[dict[str, float], list[Prediction]]:
    scored: list[Prediction] = []
    for ex, pred in zip(examples, predictions):
        scored.append(score_prediction(ex, pred, suite.scorer, client=client))

    metrics: dict[str, float] = {}
    wanted = {m.name for m in suite.metrics}
    scores = [p.score for p in scored if p.score is not None]
    if "exact_match" in wanted or "accuracy" in wanted:
        key = "exact_match" if "exact_match" in wanted else "accuracy"
        metrics[key] = float(sum(1 for p in scored if p.passed) / max(len(scored), 1))
    if "score" in wanted:
        metrics["score"] = float(sum(scores) / max(len(scores), 1)) if scores else 0.0
    latencies = [p.latency_ms for p in scored if p.latency_ms is not None]
    if "latency_ms" in wanted and latencies:
        metrics["latency_ms"] = float(sum(latencies) / len(latencies))
    tokens = [
        (p.tokens_in or 0) + (p.tokens_out or 0)
        for p in scored
        if p.tokens_in is not None or p.tokens_out is not None
    ]
    if "tokens" in wanted and tokens:
        metrics["tokens"] = float(sum(tokens) / len(tokens))
    return metrics, scored
