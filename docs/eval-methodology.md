# Evaluation methodology

**Arrives fully in Phase 6** (golden suite design, metric definitions, threshold
justifications per brief §10). Two commitments are binding already:

* **Policy-conflict escalation recall = 1.0 is a hard gate** — silently resolving an
  unresolved policy question is the one unforgivable failure in a regulated deployment.
  Outcome accuracy may be 0.85; this one may not budge. The asymmetry is the point.
* **Delta-detection P/R (target ≥ 0.7 / ≥ 0.7)** is scored against the frozen ledger in
  `data/interviews/SYNTHETIC.md`; misses and false positives get analyzed in FAILURES.md.
