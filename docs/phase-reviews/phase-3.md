# Phase 3 review — extraction, reconciliation, delta detection, graph load

**Date:** 2026-08-04 · **Scope:** transcript segmenter, case-log pattern miner, LLM
extractor with self-correction, reconciliation, delta detection + ledger scorer, Neo4j
schema/loader/queries, seed orchestrator, Demo-1 diff report, explorer v1.

## Acceptance criteria status

| Criterion | Status |
|---|---|
| Graph populated with full provenance (every Step has ≥1 DERIVED_FROM) | ⚠️ loader refuses provenance-less nodes and emits one edge per span (proven by recorder tests); the live `PROVENANCE_COVERAGE` query (0 orphans) runs inside `make seed` on real Neo4j |
| Delta detection P ≥ 0.7 and R ≥ 0.7 vs ledger | ✅ rules recover **10/10** ledger rows at P=1.00 / R=1.00 on fixture inputs, red herring excluded. ⚠️ headline number comes from `make seed` with real LLM extraction |
| Miner reproduces ledger support from raw records | ✅ lockstep test: mining `cases.jsonl` alone (no sidecar) matches every ledger count |
| Misses analyzed in FAILURES.md | ✅ D5 evidence gap found and fixed during this phase (entry added) |

72 tests green, ruff clean.

## Decisions worth defending

* **Rule-table detection, not an LLM judgment call (v1).** Every delta traces to the exact
  rule + evidence that fired — the first thing a model-risk reviewer asks. LLM-assisted
  candidate generation is roadmap.
* **Written value always wins; disagreement emits a conflict.** Attributes are never
  averaged. Practice-only parameters (`bo_scrutiny_pct`) are flagged rather than silently
  adopted as canonical.
* **Two-threshold entity resolution with an LLM adjudicator only in the ambiguous band**
  (≥0.80 merge, ≤0.55 separate). Offline runs stay conservative — unparseable adjudication
  keeps elements separate, never merges on a guess.
* **Extraction cache + dead-letter.** Re-runs are free (cost discipline) and, once the
  cache is committed post-review, a fresh clone can seed without an API key. Exhausted
  batches dead-letter with the full error chain and the pipeline continues.
* **Explorer feeds from FastAPI JSON, not neovis-over-bolt.** No database credentials in
  the browser, and a derived-file fallback means the explorer works after
  `seed_graph --skip-graph` too.

## Things Adi must be able to explain cold

1. **Line by line, what happens when an LLM output fails schema validation three times.**
   Call → `ElementBatch.model_validate_json` → `ValidationError` → re-prompt containing the
   error text *and* the offending output → span event `schema_retry_N` → after 3 attempts
   write `data/dead_letter/<source>-<ts>.json` with the whole error chain, return empty,
   pipeline continues. Tests: `test_fail_twice_then_succeed_feeds_errors_back`,
   `test_exhaustion_dead_letters_and_continues`.
2. **Why conflicting sources become Delta nodes instead of being resolved.** Silently siding
   with practice ships an undocumented rule as if it were policy; silently siding with policy
   erases the control knowledge that keeps the practice safe. Both destroy the audit trail.
3. **Why ground truth is a sidecar.** If labels lived in `cases.jsonl`, the miner would grade
   itself on leaked answers and the P/R number would be theatre.
4. **Why error cases must NOT produce deltas.** A pattern needs support; a mistake is noise.
   Rules require trigger *and* practiced response together — that's what keeps E5/E6 out.
5. **When graph expansion beats pure vector search.** `step_clause_ids` pulls clauses already
   linked to the step plus 1-hop neighbors: for "callback verification", the vector query
   matches CIP text about verification generally, but the graph knows *this* step derives
   from FFIEC-CIP-¶7 and is governed by a control with its own clause.

## Carry-forward

* `make seed` on the dev machine (needs API key + `make up`): record real P/R here, commit
  `data/extracted/` after reviewing it, screenshot the explorer for the README.
* Any detection miss/false positive from the real run → FAILURES.md.
