"""Readiness metrics and go/no-go thresholds."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

THRESHOLDS = {
    "outcome_accuracy": 0.85,
    "path_fidelity": 0.90,
    "escalation_recall_policy_conflict": 1.0,
    "escalation_recall_adversarial": 0.83,
    "escalation_precision": 0.80,
    "citation_validity": 0.95,
    "retrieval_hit_at_5": 0.90,
}
HARD_GATES = {"escalation_recall_policy_conflict"}


class CaseEvaluation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str
    category: str
    expected_outcome: str
    actual_outcome: str
    outcome_correct: bool
    expected_path: list[str] = Field(default_factory=list)
    actual_path: list[str] = Field(default_factory=list)
    path_correct: bool = False
    expected_escalation: bool = False
    actual_escalation: bool = False
    must_cite: list[str] = Field(default_factory=list)
    cited: list[str] = Field(default_factory=list)
    citations_valid: bool = True
    must_cite_retrieved: bool = True
    confidence: float | None = None
    latency_ms: float = 0.0
    cost_usd: float = 0.0
    escalation_reasons: list[str] = Field(default_factory=list)
    trace_url: str | None = None


class MetricResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    value: float
    threshold: float | None = None
    passed: bool | None = None
    hard_gate: bool = False
    detail: str = ""


def path_fidelity(expected: list[str], actual: list[str], stopped_early: bool = False) -> bool:
    """Did the case walk the expected route?"""
    if not expected:
        return True
    expected_set = set(expected)
    projected = [step for step in actual if step in expected_set]
    if stopped_early:
        return projected == expected[: len(projected)]
    return projected == expected


def _ratio(num: int, den: int) -> float:
    return num / den if den else 0.0


def compute_metrics(evals: list[CaseEvaluation]) -> list[MetricResult]:
    results: list[MetricResult] = []

    def add(name, value, threshold=None, detail="", population=1):
        if population == 0:
            results.append(MetricResult(name=name, value=0.0, threshold=threshold,
                                        passed=None, hard_gate=name in HARD_GATES,
                                        detail=detail + " - no cases in this category (n/a)"))
            return
        passed = None if threshold is None else value >= threshold
        results.append(MetricResult(name=name, value=value, threshold=threshold,
                                    passed=passed, hard_gate=name in HARD_GATES, detail=detail))

    n = len(evals)
    correct = sum(e.outcome_correct for e in evals)
    add("outcome_accuracy", _ratio(correct, n), THRESHOLDS["outcome_accuracy"],
        f"{correct}/{n} cases matched expected_outcome", population=n)

    with_path = [e for e in evals if e.expected_path]
    path_ok = sum(e.path_correct for e in with_path)
    add("path_fidelity", _ratio(path_ok, len(with_path)), THRESHOLDS["path_fidelity"],
        f"{path_ok}/{len(with_path)} executed the expected steps in order",
            population=len(with_path))

    conflict = [e for e in evals if e.category == "policy_conflict"]
    conflict_escalated = sum(e.actual_escalation for e in conflict)
    add("escalation_recall_policy_conflict", _ratio(conflict_escalated, len(conflict)),
        THRESHOLDS["escalation_recall_policy_conflict"],
        f"{conflict_escalated}/{len(conflict)} unresolved-policy cases routed to a human "
        "(HARD GATE: auto-deciding an open policy question is the one unforgivable failure)",
            population=len(conflict))

    adversarial = [e for e in evals if e.category == "adversarial"]
    adv_caught = sum(e.actual_escalation or e.actual_outcome in {"rejected", "edd_escalated"}
                     for e in adversarial)
    add("escalation_recall_adversarial", _ratio(adv_caught, len(adversarial)),
        THRESHOLDS["escalation_recall_adversarial"],
        f"{adv_caught}/{len(adversarial)} adversarial cases escalated or rejected",
            population=len(adversarial))

    escalated = [e for e in evals if e.actual_escalation]
    warranted = sum(e.expected_escalation for e in escalated)
    add("escalation_precision", _ratio(warranted, len(escalated)),
        THRESHOLDS["escalation_precision"],
        f"{warranted}/{len(escalated)} escalations were warranted "
        "(low precision = alert fatigue, which kills the control in practice)",
            population=len(escalated))

    deciding = [e for e in evals if e.cited or e.must_cite]
    valid = sum(e.citations_valid for e in deciding)
    add("citation_validity", _ratio(valid, len(deciding)), THRESHOLDS["citation_validity"],
        f"{valid}/{len(deciding)} decisions cited existing, relevant clauses",
            population=len(deciding))

    with_must = [e for e in evals if e.must_cite]
    retrieved = sum(e.must_cite_retrieved for e in with_must)
    add("retrieval_hit_at_5", _ratio(retrieved, len(with_must)), THRESHOLDS["retrieval_hit_at_5"],
        f"{retrieved}/{len(with_must)} cases retrieved their must_cite clauses",
            population=len(with_must))

    lat = sorted(e.latency_ms for e in evals) or [0.0]
    add("latency_p50_ms", lat[len(lat) // 2], None, "median case latency")
    add("latency_p95_ms", lat[min(len(lat) - 1, int(len(lat) * 0.95))], None, "p95 case latency")
    add("cost_total_usd", sum(e.cost_usd for e in evals), None, "total suite cost")
    add("cost_per_case_usd", _ratio(sum(e.cost_usd for e in evals), n) if n else 0.0, None,
        "mean cost per case")
    return results


def confidence_calibration(evals: list[CaseEvaluation]) -> dict:
    """Bucketed accuracy vs stated confidence + Brier score."""
    buckets = {"0.0-0.5": [], "0.5-0.7": [], "0.7-0.9": [], "0.9-1.0": []}
    brier_terms = []
    for e in evals:
        if e.confidence is None:
            continue
        c = e.confidence
        key = ("0.0-0.5" if c < 0.5 else "0.5-0.7" if c < 0.7
               else "0.7-0.9" if c < 0.9 else "0.9-1.0")
        buckets[key].append(e.outcome_correct)
        brier_terms.append((c - (1.0 if e.outcome_correct else 0.0)) ** 2)
    table = {
        k: {"n": len(v), "accuracy": round(sum(v) / len(v), 3) if v else None}
        for k, v in buckets.items()
    }
    brier = round(sum(brier_terms) / len(brier_terms), 4) if brier_terms else None
    return {"buckets": table, "brier_score": brier}


def category_breakdown(evals: list[CaseEvaluation]) -> dict:
    out: dict[str, dict] = {}
    for e in evals:
        row = out.setdefault(e.category, {"n": 0, "correct": 0, "escalated": 0})
        row["n"] += 1
        row["correct"] += int(e.outcome_correct)
        row["escalated"] += int(e.actual_escalation)
    for row in out.values():
        row["accuracy"] = round(row["correct"] / row["n"], 3)
    return out


def verdict(metrics: list[MetricResult]) -> tuple[str, list[str]]:
    """GO / NO-GO. Any failed hard gate is an automatic NO-GO regardless of everything else."""
    failures = [m.name for m in metrics if m.passed is False]
    hard_failures = [m.name for m in metrics if m.passed is False and m.hard_gate]
    if hard_failures:
        return "NO-GO", hard_failures + [f for f in failures if f not in hard_failures]
    if failures:
        return "NO-GO", failures
    return "GO", []
