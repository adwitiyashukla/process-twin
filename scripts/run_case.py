"""Run one case end to end through the compiled workflow (brief §3).

    uv run python scripts/run_case.py --case GC-003            # golden-suite case
    uv run python scripts/run_case.py --case GC-017 --auto-approve
    uv run python scripts/run_case.py --case GC-003 --temporal  # durable execution

Without --temporal this runs the standalone executor (same semantics, no infra needed) —
which is also what the eval runner uses.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, "src")

import yaml  # noqa: E402

from process_twin.config import get_settings  # noqa: E402
from process_twin.observability import tracing  # noqa: E402
from process_twin.runtime.executor import execute_case  # noqa: E402
from process_twin.schemas.audit import AuditLog  # noqa: E402

SUITE = Path("data/golden_cases/suite.yaml")


def load_spec_and_deltas():
    """Compile from data/derived (produced by `make seed`), else the documented fallback
    process so `run-case` works before a full seed."""
    from process_twin.runtime.compiler import compile_workflow

    derived = Path("data/derived")
    deltas = []
    if (derived / "deltas.json").exists():
        deltas = json.loads((derived / "deltas.json").read_text(encoding="utf-8"))
    if (derived / "canonicals.json").exists():
        canonicals = json.loads((derived / "canonicals.json").read_text(encoding="utf-8"))
        steps = [{"id": c["id"], "name": c["name"], "step_type": "task",
                  "sequence_hint": c.get("sequence_hint"), "evidence_required": [],
                  "controls": [], "next": []}
                 for c in canonicals if c["element_type"] == "step"]
        if steps:
            ordered = sorted(steps, key=lambda s: (s["sequence_hint"] is None,
                                                   s["sequence_hint"] or 0))
            for a, b in zip(ordered, ordered[1:], strict=False):
                a["next"] = [{"target": b["id"], "condition": None}]
            return compile_workflow({"steps": ordered, "deltas": deltas}), deltas
    from process_twin.evaluation.runner import reference_process

    return compile_workflow(reference_process(deltas)), deltas


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", required=True)
    ap.add_argument("--auto-approve", action="store_true",
                    help="scripted reviewer approves every gate (demo/eval convenience)")
    ap.add_argument("--temporal", action="store_true", help="run durably via Temporal")
    args = ap.parse_args()

    suite = yaml.safe_load(SUITE.read_text(encoding="utf-8"))
    case = next((c for c in suite["cases"] if c["id"] == args.case), None)
    if case is None:
        print(f"unknown case {args.case}; available: {[c['id'] for c in suite['cases'][:5]]}…")
        return 1

    if args.temporal:
        from temporalio.client import Client

        from process_twin.durability.workflows import CaseWorkflow, CaseWorkflowInput

        async def go():
            settings = get_settings()
            client = await Client.connect(settings.temporal_address,
                                          namespace=settings.temporal_namespace)
            handle = await client.start_workflow(
                CaseWorkflow.run,
                CaseWorkflowInput(case_id=case["id"], applicant=case["input"]),
                id=f"case-{case['id']}", task_queue=settings.temporal_task_queue,
            )
            print(f"started workflow {handle.id} — watch http://localhost:8233")
            return await handle.result()

        print(json.dumps(asyncio.run(go()), indent=2))
        return 0

    spec, deltas = load_spec_and_deltas()
    trace = tracing.start_case_trace(case["id"], golden_case_id=case["id"], phase="4")
    resolver = (lambda *a, **k: "approve") if args.auto_approve else None
    result = execute_case(spec, case["id"], case["input"], deltas=deltas,
                          approval_resolver=resolver, audit=AuditLog(), trace=trace)
    tracing.flush()

    print(json.dumps(result.model_dump(mode="json"), indent=2)[:2000])
    print(f"\noutcome: {result.outcome}   expected: {case['expected_outcome']}")
    print(f"escalated: {result.escalated}   reasons: {result.escalation_reasons}")
    print(f"citations: {result.citations}")
    print("audit trail: uv run python scripts/replay_case.py " + case["id"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
