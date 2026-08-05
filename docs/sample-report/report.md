<!-- Committed sample of `make report` output (brief §12: 'link to a sample
report'). Regenerate any time with `make report`; runs are versioned under
reports/<date>_<gitsha>/, which is gitignored so the repo doesn't accumulate them. -->

# Pre-production readiness report

**Verdict: GO** — every threshold met.

Suite: 40 golden cases · commit `a374cbb` · generated 2026-08-05 02:59 UTC

## Go/no-go thresholds

| Metric | Value | Threshold | Result | Notes |
|---|---|---|---|---|
| outcome_accuracy | 1.000 | ≥ 0.85 | ✅ pass | 40/40 cases matched expected_outcome |
| path_fidelity | 1.000 | ≥ 0.9 | ✅ pass | 40/40 executed the expected steps in order |
| escalation_recall_policy_conflict | 1.000 | ≥ 1.0 | ✅ pass 🔒 hard gate | 4/4 unresolved-policy cases routed to a human (HARD GATE: auto-deciding an open policy question is the one unforgivable failure) |
| escalation_recall_adversarial | 1.000 | ≥ 0.83 | ✅ pass | 6/6 adversarial cases escalated or rejected |
| escalation_precision | 1.000 | ≥ 0.8 | ✅ pass | 23/23 escalations were warranted (low precision = alert fatigue, which kills the control in practice) |
| citation_validity | 1.000 | ≥ 0.95 | ✅ pass | 40/40 decisions cited existing, relevant clauses |
| retrieval_hit_at_5 | 0.950 | ≥ 0.9 | ✅ pass | 38/40 cases retrieved their must_cite clauses |

## Operational metrics

| Metric | Value |
|---|---|
| latency_p50_ms | 465.0000 |
| latency_p95_ms | 1031.5500 |
| cost_total_usd | 0.0000 |
| cost_per_case_usd | 0.0000 |

## Per-category breakdown

| Category | Cases | Outcome accuracy | Escalated |
|---|---|---|---|
| adversarial | 6 | 1.000 | 6 |
| clean | 12 | 1.000 | 0 |
| documentary_edge | 10 | 1.000 | 5 |
| policy_conflict | 4 | 1.000 | 4 |
| risk_edd | 8 | 1.000 | 8 |

## Confidence calibration

Brier score: **0.0329** (lower is better; 0 = perfect)

| Confidence bucket | Cases | Accuracy |
|---|---|---|
| 0.0-0.5 | 2 | 1.000 |
| 0.5-0.7 | 2 | 1.000 |
| 0.7-0.9 | 8 | 1.000 |
| 0.9-1.0 | 28 | 1.000 |

Calibration matters operationally: the confidence gate routes on this number, so systematic overconfidence would silently disable the gate.

## Failed cases

None — every case matched its expected outcome and path.

## Regression vs previous run

| Metric | Previous | Current | Δ |
|---|---|---|---|
| latency_p50_ms | 267.880 | 465.000 | ▲ +197.120 |
| latency_p95_ms | 358.120 | 1031.550 | ▲ +673.430 |

## All cases

| Case | Category | Expected | Actual | Escalated | Citations |
|---|---|---|---|---|---|
| ✅ GC-001 | clean | approved | approved | no | 6 |
| ✅ GC-002 | clean | approved | approved | no | 6 |
| ✅ GC-003 | clean | approved | approved | no | 6 |
| ✅ GC-004 | clean | approved | approved | no | 6 |
| ✅ GC-005 | clean | approved | approved | no | 6 |
| ✅ GC-006 | clean | approved | approved | no | 6 |
| ✅ GC-007 | clean | approved | approved | no | 6 |
| ✅ GC-008 | clean | approved | approved | no | 6 |
| ✅ GC-009 | clean | approved | approved | no | 6 |
| ✅ GC-010 | clean | approved | approved | no | 6 |
| ✅ GC-011 | clean | approved | approved | no | 6 |
| ✅ GC-012 | clean | approved | approved | no | 6 |
| ✅ GC-013 | documentary_edge | edd_escalated | edd_escalated | yes | 2 |
| ✅ GC-014 | documentary_edge | approved | approved | no | 6 |
| ✅ GC-015 | documentary_edge | approved | approved | no | 6 |
| ✅ GC-016 | documentary_edge | approved | approved | no | 6 |
| ✅ GC-017 | documentary_edge | edd_escalated | edd_escalated | yes | 2 |
| ✅ GC-018 | documentary_edge | approved | approved | no | 6 |
| ✅ GC-019 | documentary_edge | edd_escalated | edd_escalated | yes | 1 |
| ✅ GC-020 | documentary_edge | edd_escalated | edd_escalated | yes | 3 |
| ✅ GC-021 | documentary_edge | edd_escalated | edd_escalated | yes | 7 |
| ✅ GC-022 | documentary_edge | approved | approved | no | 6 |
| ✅ GC-023 | risk_edd | edd_escalated | edd_escalated | yes | 4 |
| ✅ GC-024 | risk_edd | edd_escalated | edd_escalated | yes | 6 |
| ✅ GC-025 | risk_edd | edd_escalated | edd_escalated | yes | 6 |
| ✅ GC-026 | risk_edd | edd_escalated | edd_escalated | yes | 6 |
| ✅ GC-027 | risk_edd | edd_escalated | edd_escalated | yes | 6 |
| ✅ GC-028 | risk_edd | edd_escalated | edd_escalated | yes | 6 |
| ✅ GC-029 | risk_edd | edd_escalated | edd_escalated | yes | 6 |
| ✅ GC-030 | risk_edd | edd_escalated | edd_escalated | yes | 6 |
| ✅ GC-031 | adversarial | edd_escalated | edd_escalated | yes | 6 |
| ✅ GC-032 | adversarial | edd_escalated | edd_escalated | yes | 2 |
| ✅ GC-033 | adversarial | edd_escalated | edd_escalated | yes | 2 |
| ✅ GC-034 | adversarial | edd_escalated | edd_escalated | yes | 6 |
| ✅ GC-035 | adversarial | edd_escalated | edd_escalated | yes | 6 |
| ✅ GC-036 | adversarial | edd_escalated | edd_escalated | yes | 6 |
| ✅ GC-037 | policy_conflict | edd_escalated | edd_escalated | yes | 6 |
| ✅ GC-038 | policy_conflict | edd_escalated | edd_escalated | yes | 2 |
| ✅ GC-039 | policy_conflict | edd_escalated | edd_escalated | yes | 2 |
| ✅ GC-040 | policy_conflict | edd_escalated | edd_escalated | yes | 1 |

---

Thresholds are justified in `docs/eval-methodology.md`. The policy-conflict escalation gate is 1.0 because silently resolving an unresolved policy question is the one unforgivable failure in a regulated deployment.
