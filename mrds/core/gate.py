"""CI gate policy over comparison results."""

from __future__ import annotations

from dataclasses import dataclass, field

from mrds.core.compare import ComparisonResult, MetricDelta


@dataclass
class GateResult:
    passed: bool
    comparison: ComparisonResult
    message: str
    breached: list[MetricDelta] = field(default_factory=list)


class GatePolicy:
    def evaluate(self, comparison: ComparisonResult) -> GateResult:
        breached = comparison.breached_metrics
        if not breached:
            return GateResult(
                passed=True,
                comparison=comparison,
                message=f"GATE PASS: {comparison.suite_name} "
                f"({comparison.candidate_run_id} vs {comparison.baseline_run_id})",
                breached=[],
            )
        lines = [
            f"GATE FAIL: {comparison.suite_name} "
            f"({comparison.candidate_run_id} vs {comparison.baseline_run_id})",
        ]
        for m in breached:
            lines.append(
                f"  - {m.name}: baseline={m.baseline:.6f} candidate={m.candidate:.6f} "
                f"delta={m.delta:.6f} ({m.reason})"
            )
        return GateResult(
            passed=False,
            comparison=comparison,
            message="\n".join(lines),
            breached=breached,
        )
