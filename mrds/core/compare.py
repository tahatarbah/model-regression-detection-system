"""Compare baseline vs candidate runs and compute metric deltas."""

from __future__ import annotations

from dataclasses import dataclass, field

from mrds.core.schema import MetricConfig, MetricDirection, ThresholdConfig


@dataclass
class MetricDelta:
    name: str
    baseline: float
    candidate: float
    delta: float
    relative_delta: float | None
    direction: MetricDirection
    breached: bool
    reason: str | None = None


@dataclass
class ExampleDiff:
    example_id: str
    baseline_output: object
    candidate_output: object
    baseline_score: float | None
    candidate_score: float | None
    baseline_passed: bool | None
    candidate_passed: bool | None
    regressed: bool


@dataclass
class ComparisonResult:
    baseline_run_id: str
    candidate_run_id: str
    suite_name: str
    metric_deltas: list[MetricDelta] = field(default_factory=list)
    example_diffs: list[ExampleDiff] = field(default_factory=list)
    passed: bool = True

    @property
    def breached_metrics(self) -> list[MetricDelta]:
        return [m for m in self.metric_deltas if m.breached]


def _is_breach(
    baseline: float,
    candidate: float,
    direction: MetricDirection,
    threshold: ThresholdConfig,
) -> tuple[bool, str | None]:
    delta = candidate - baseline
    if direction == MetricDirection.HIGHER_IS_BETTER:
        degradation = baseline - candidate  # positive when worse
    else:
        degradation = candidate - baseline

    reasons: list[str] = []
    breached = False

    if threshold.absolute is not None and degradation > threshold.absolute:
        breached = True
        reasons.append(
            f"absolute degradation {degradation:.6f} > {threshold.absolute}"
        )

    if threshold.relative is not None:
        denom = abs(baseline) if baseline != 0 else 1e-12
        rel = degradation / denom
        if rel > threshold.relative:
            breached = True
            reasons.append(
                f"relative degradation {rel:.6f} > {threshold.relative}"
            )

    # If no thresholds configured, any degradation is a breach
    if threshold.absolute is None and threshold.relative is None:
        if degradation > 0:
            breached = True
            reasons.append(f"degradation {degradation:.6f} with no threshold")

    return breached, "; ".join(reasons) if reasons else None


class CompareEngine:
    def compare_metrics(
        self,
        *,
        baseline_metrics: dict[str, float],
        candidate_metrics: dict[str, float],
        metric_configs: list[MetricConfig],
        baseline_run_id: str,
        candidate_run_id: str,
        suite_name: str,
    ) -> ComparisonResult:
        deltas: list[MetricDelta] = []
        for cfg in metric_configs:
            if cfg.name not in baseline_metrics or cfg.name not in candidate_metrics:
                continue
            b = float(baseline_metrics[cfg.name])
            c = float(candidate_metrics[cfg.name])
            delta = c - b
            rel = (delta / abs(b)) if b != 0 else None
            breached, reason = _is_breach(b, c, cfg.direction, cfg.threshold)
            deltas.append(
                MetricDelta(
                    name=cfg.name,
                    baseline=b,
                    candidate=c,
                    delta=delta,
                    relative_delta=rel,
                    direction=cfg.direction,
                    breached=breached,
                    reason=reason,
                )
            )

        result = ComparisonResult(
            baseline_run_id=baseline_run_id,
            candidate_run_id=candidate_run_id,
            suite_name=suite_name,
            metric_deltas=deltas,
            passed=not any(d.breached for d in deltas),
        )
        return result

    def attach_example_diffs(
        self,
        result: ComparisonResult,
        baseline_examples: list[dict],
        candidate_examples: list[dict],
    ) -> ComparisonResult:
        by_id_b = {e["example_id"]: e for e in baseline_examples}
        by_id_c = {e["example_id"]: e for e in candidate_examples}
        ids = sorted(set(by_id_b) | set(by_id_c))
        diffs: list[ExampleDiff] = []
        for eid in ids:
            b = by_id_b.get(eid, {})
            c = by_id_c.get(eid, {})
            b_pass = b.get("passed")
            c_pass = c.get("passed")
            b_score = b.get("score")
            c_score = c.get("score")
            regressed = False
            if b_pass is True and c_pass is False:
                regressed = True
            elif (
                b_score is not None
                and c_score is not None
                and float(c_score) < float(b_score)
            ):
                regressed = True
            diffs.append(
                ExampleDiff(
                    example_id=eid,
                    baseline_output=b.get("output"),
                    candidate_output=c.get("output"),
                    baseline_score=b_score,
                    candidate_score=c_score,
                    baseline_passed=b_pass,
                    candidate_passed=c_pass,
                    regressed=regressed,
                )
            )
        result.example_diffs = diffs
        return result
