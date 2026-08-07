"""Golden-suite executor."""

from __future__ import annotations

import json
import time
from pathlib import Path

import yaml

from process_twin.evaluation.metrics import CaseEvaluation, path_fidelity
from process_twin.runtime import guardrails
from process_twin.runtime.compiler import WorkflowSpec, compile_workflow
from process_twin.runtime.executor import execute_case
from process_twin.schemas.audit import AuditLog

SUITE_PATH = Path("data/golden_cases/suite.yaml")
DERIVED = Path("data/derived")

REFERENCE_STEPS = [
    ("EL-collect", "collect customer information", 1),
    ("EL-verify", "verify identity documents", 2),
    ("EL-callback", "callback verification", 3),
    ("EL-screen", "screen sanctions and pep lists", 4),
    ("EL-juris", "assess jurisdiction risk", 5),
    ("EL-bo", "check beneficial ownership", 6),
    ("EL-rate", "compute risk rating", 7),
    ("EL-edd", "determine edd requirement", 8),
    ("EL-decide", "final onboarding decision", 9),
]


def reference_process(deltas: list[dict] | None = None) -> dict:
    steps = []
    for i, (sid, name, seq) in enumerate(REFERENCE_STEPS):
        nxt = ([{"target": REFERENCE_STEPS[i + 1][0], "condition": None}]
               if i + 1 < len(REFERENCE_STEPS) else [])
        steps.append({"id": sid, "name": name, "sequence_hint": seq, "step_type": "task",
                      "evidence_required": [], "controls": [], "next": nxt})
    return {"steps": steps, "deltas": deltas or []}


def load_process() -> tuple[WorkflowSpec, list[dict]]:
    deltas = []
    if (DERIVED / "deltas.json").exists():
        deltas = json.loads((DERIVED / "deltas.json").read_text(encoding="utf-8"))
    if (DERIVED / "canonicals.json").exists():
        canonicals = json.loads((DERIVED / "canonicals.json").read_text(encoding="utf-8"))
        steps = [{"id": c["id"], "name": c["name"], "sequence_hint": c.get("sequence_hint"),
                  "step_type": "task", "evidence_required": [], "controls": [], "next": []}
                 for c in canonicals if c["element_type"] == "step"]
        if len(steps) >= 3:
            ordered = sorted(steps, key=lambda s: (s["sequence_hint"] is None,
                                                   s["sequence_hint"] or 0))
            for a, b in zip(ordered, ordered[1:], strict=False):
                a["next"] = [{"target": b["id"], "condition": None}]
            return compile_workflow({"steps": ordered, "deltas": deltas}), deltas
    return compile_workflow(reference_process(deltas)), deltas


def known_clause_ids() -> set[str]:
    ids: set[str] = set()
    processed = Path("data/policies/processed")
    for f in processed.glob("*.jsonl"):
        for line in f.read_text(encoding="utf-8").splitlines():
            if line.strip():
                ids.add(json.loads(line)["clause_id"])
    if not ids:
        from process_twin.runtime.atoms import CLAUSES

        ids = set(CLAUSES.values())
    return ids


def run_suite(suite_path: Path = SUITE_PATH, audit_path: Path | None = None,
              trace_base: str | None = None) -> list[CaseEvaluation]:
    suite = yaml.safe_load(suite_path.read_text(encoding="utf-8"))
    spec, deltas = load_process()
    validator = guardrails.CitationValidator(known_clause_ids())
    audit = AuditLog(audit_path) if audit_path else None

    evaluations: list[CaseEvaluation] = []
    for case in suite["cases"]:
        start = time.perf_counter()
        result = execute_case(spec, case["id"], case["input"], deltas=deltas,
                              validator=validator, approval_resolver=None, audit=audit)
        elapsed_ms = (time.perf_counter() - start) * 1000

        cited = result.citations
        must = case.get("must_cite", [])
        citations_valid = all(
            validator.validate(r.output).passed
            for r in result.records if r.output and r.output.citations
        ) if any(r.output and r.output.citations for r in result.records) else True
        confidences = [r.output.confidence for r in result.records if r.output]

        evaluations.append(CaseEvaluation(
            case_id=case["id"], category=case["category"],
            expected_outcome=case["expected_outcome"], actual_outcome=result.outcome,
            outcome_correct=result.outcome == case["expected_outcome"],
            expected_path=case.get("expected_path", []), actual_path=result.path,
            path_correct=path_fidelity(
                case.get("expected_path", []), result.path,
                stopped_early=result.outcome in {"edd_escalated", "rejected",
                                                 "pending_information"},
            ),
            expected_escalation=case.get("expected_escalation", False),
            actual_escalation=result.escalated,
            must_cite=must, cited=cited,
            citations_valid=citations_valid,
            must_cite_retrieved=all(m in cited for m in must) if must else True,
            confidence=(sum(confidences) / len(confidences)) if confidences else None,
            latency_ms=round(elapsed_ms, 2),
            cost_usd=0.0,
            escalation_reasons=result.escalation_reasons,
            trace_url=f"{trace_base}?caseId={case['id']}" if trace_base else None,
        ))
    return evaluations
