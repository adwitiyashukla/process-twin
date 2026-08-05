"""Demo 2: run the golden suite and generate the readiness report (`make report`)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, "src")

from process_twin.evaluation.metrics import compute_metrics, verdict  # noqa: E402
from process_twin.evaluation.report import generate  # noqa: E402
from process_twin.evaluation.runner import run_suite  # noqa: E402


def main() -> int:
    print("running the 40-case golden suite…")
    evals = run_suite(audit_path=Path("data/audit/eval_audit_log.jsonl"),
                      trace_base="http://localhost:3000/traces")
    metrics = compute_metrics(evals)
    status, failures = verdict(metrics)
    run_dir = generate(evals)

    for m in metrics:
        if m.threshold is not None:
            print(f"  {'PASS' if m.passed else 'FAIL'}  {m.name:38} {m.value:.3f} "
                  f"(>= {m.threshold}){'  [HARD GATE]' if m.hard_gate else ''}")
    print(f"\nVERDICT: {status}" + (f" — failed: {', '.join(failures)}" if failures else ""))
    print(f"report: {run_dir}/report.html  (+ report.md, summary.json)")
    return 0 if status == "GO" else 1


if __name__ == "__main__":
    sys.exit(main())
