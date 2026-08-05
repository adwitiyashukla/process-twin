# Phase 4–6 review — governed runtime, durability, readiness report

**Date:** 2026-08-05 · **Scope:** compiler + atoms + guardrails + HITL (P4), hash-chained
audit + Temporal (P5), golden suite + metrics + readiness report (P6).

## Acceptance criteria status

| Phase | Criterion | Status |
|---|---|---|
| 4 | Clean case runs straight-through with ≥95% citation validity | ✅ 12/12 clean cases straight through, citation validity 1.00 |
| 4 | Boundary case interrupts, is approved, resumes, completes | ✅ `test_approved_gate_resumes_the_case`; live via `POST /approvals/{id}/decide` ⚠️ (needs `make api`) |
| 4 | Guardrail tests prove the delta guard and citation validator block what they must | ✅ `test_delta_forces_human`, `test_high_confidence_cannot_override_delta_guard`, both citation failure modes |
| 5 | Audit replay reconstructs a full case; determinism verified | ✅ replay + chain verification tested; determinism enforced in CI by AST analysis |
| 5 | `demo_durability.sh` passes 3 consecutive runs | ⚠️ **environment-bound** — script written; needs Docker + worker on the dev machine |
| 6 | `make report` produces the versioned report | ✅ HTML + MD + summary.json under `reports/<date>_<sha>/` |
| 6 | Policy-conflict escalation recall = 1.0, other thresholds met | ✅ **VERDICT: GO** — every threshold met on the first full run after fixes |

126 tests green, ruff clean, determinism check green.

## Decisions worth defending

* **The compiler emits a data structure, not a graph object.** `WorkflowSpec` is plain
  Pydantic; `to_langgraph()` is a separate function. Every compile rule is therefore
  testable without importing LangGraph, and the eval runner executes the spec directly.
* **Cycles rejected, not supported.** A cyclic KYC process makes path fidelity and
  termination guarantees meaningless, and the thing people actually want cycles *for* —
  retries — belongs to the Temporal retry policy where it gets backoff and a cap.
* **Atoms are deterministic where auditability demands it.** Thresholds, ownership maths
  and list logic are code, not model output: an examiner can re-derive every threshold
  decision by hand, and eval numbers don't drift with sampling. The LLM seam exists for
  where judgment is genuinely required.
* **Eval runs the production executor.** Not a parallel evaluation path — otherwise the
  report measures code that never ships.
* **No auto-approval during eval.** A gate is recorded as an escalation and the case stops.
  Inventing a reviewer decision would inflate accuracy with decisions no human made.
* **A written trigger is a predicate over the case, never a threshold on a score.** Learned
  the hard way (FAILURES.md): two policy triggers had been folded into an additive risk
  score and silently stopped firing.

## Things Adi must be able to explain cold

1. **Why must LLM calls live in activities, never in workflow code?** Temporal rebuilds
   workflow state by *replaying* the workflow function against recorded history. Activity
   results are read back from history rather than recomputed; anything non-deterministic in
   the workflow body would take a different path on replay — non-determinism error, or
   silent divergence. `scripts/check_determinism.py` enforces this by AST analysis in CI.
2. **Kill-and-restart: what does Temporal persist, and what do you persist on top?**
   Temporal persists workflow history (inputs, activity results, signals, timers). On top
   of that: the hash-chained audit log (governance evidence, independent of Temporal) and
   the approvals store (the human queue). Duplicate audit events would come from an
   activity that wrote its event then failed before ACKing — prevented by keying the write
   on `(case_id, step_id, event_type)` and returning the existing hash on retry.
3. **The citation guardrail's two failure modes.** Fabricated clause ID → caught by the
   existence check, appears in Langfuse as `citation_unknown_clause`. Real-but-irrelevant
   clause → caught by the reranker relevance floor, appears as `citation_irrelevant`. The
   second is the subtle one and the reason existence alone isn't enough.
4. **Why can't high confidence override the delta guard?** Confidence measures how sure the
   model is about its own reasoning. It says nothing about which side of a question the
   *institution* hasn't answered. A 0.99-confidence decision on an unresolved policy
   conflict is the most dangerous output the system can produce.
5. **Defend the threshold asymmetry (0.85 vs 1.0).** See README and eval-methodology — the
   argument is about the *shape* of the failure, not its rate.
6. **What's the first thing that breaks at 10k cases/day?** Activity fan-out against a
   single worker and the audit log's read-modify-write on every append (it reads the whole
   file to get the previous hash). Fixes in order: partition workers by task queue; keep the
   chain head in memory/Redis with periodic checkpointing; cache retrieval per clause set;
   Neo4j read replicas for the graph-expansion queries.

## Carry-forward

* `make demo-durability` on the dev machine, three consecutive runs (Phase 5 acceptance).
* Live HITL round-trip through the API with Temporal signalling (Phase 4 acceptance).
* `make seed` with a real API key → real delta-detection P/R for the README.
* Record the demo video per `docs/demo-script.md`.
