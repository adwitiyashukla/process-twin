# Evaluation methodology

How the golden suite is built, what each metric means, and why every threshold sits where
it does (brief §10). Numbers in the README come from `make report`, which writes a
versioned report under `reports/<date>_<gitsha>/`.

## Golden suite design (40 cases)

| Category | n | What it measures |
|---|---|---|
| clean | 12 | **False-positive escalation.** A governance system that escalates everything is useless — reviewers stop reading. These must run straight through. |
| documentary edge | 10 | Real-world document messiness: expired ID + renewal receipt, maiden-name mismatch, transliterated names, address mismatches, PO boxes, boundary-age proof of address, foreign tax IDs. |
| risk / EDD | 8 | Written escalation triggers: PEP direct and close-associate, beneficial ownership at and around the 25% line, complex ownership, adverse media, high-risk jurisdictions. |
| adversarial | 6 | Deliberate evasion: structuring-adjacent funding, synthetic-identity signals, document tampering, straw-man owners, rapid resubmission, purpose/activity mismatch. |
| policy conflict | 4 | Cases landing **exactly** on unresolved deltas (D1, D2, D9, D10). The system must route to a human — never auto-decide. |

Each case is a real fact pattern, not a permutation: `targets_delta` links the case to the
ledger row it exercises, so a failure points at a specific governance question, not a
generic score drop.

## Metric definitions

**Outcome accuracy** — final decision equals `expected_outcome`. Threshold **0.85**.
Not 1.0: an ordinary case decided wrongly is a quality problem — measurable, improvable,
and visible in the report. Demanding perfection here would push toward overfitting the
suite, which teaches you nothing about the next 40 cases.

**Path fidelity** — did the case walk the expected route? Threshold **0.90**. Measured
over the *expected steps only*: the compiled workflow legitimately runs steps a given case
doesn't care about (the callback control runs for everyone; beneficial-ownership runs for
individuals and returns "not applicable"). Two regimes:

* ran to completion → the projection of the actual path onto the expected set must equal
  the expected route exactly;
* stopped early at a gate → that projection must be an in-order **prefix**.

The prefix rule exists because a workflow that halts for a human has not failed. Scoring a
correct escalation as a path failure would tune the thresholds toward rewarding
straight-through processing — exactly backwards for a governance system.

**Escalation recall, policy-conflict — threshold 1.0, HARD GATE.**
This is the asymmetry to defend. Outcome accuracy tolerates 15% error; this tolerates
none. The reason is the *shape* of the failure, not its rate. When the system decides an
ordinary case wrongly, it produces a wrong answer that review can catch. When it silently
resolves a question the institution itself has not resolved — the written rule says 25%,
the floor practises 20%, and nobody has decided which governs — it produces a
**confidently-wrong decision with a clean audit trail**, having invented policy on a
customer's file. That is not a quality defect; it is the system exceeding its authority.
No amount of accuracy elsewhere compensates, so it gates the release outright.

**Escalation recall, adversarial** — threshold **0.83** (5 of 6). Adversarial patterns are
open-ended and detection is genuinely hard; one miss is tolerable, two means the signals
aren't wired properly.

**Escalation precision** — threshold **0.80**. The counterweight to the recall gates.
Low precision means alert fatigue, and a control that reviewers learn to rubber-stamp has
been disabled in practice while still looking green on a dashboard.

**Citation validity** — threshold **0.95**. Every decision must cite a clause that exists
*and* is relevant. Two failure modes, both caught: a fabricated clause ID (existence
check), and a real-but-irrelevant clause (reranker relevance check).

**Retrieval hit@5** — threshold **0.90**. The `must_cite` clauses have to actually reach
the deciding atom. A governance guardrail can only validate what retrieval surfaced.

**Confidence calibration** — reported, not gated (bucketed accuracy + Brier score).
Operationally load-bearing: the confidence gate routes on this number, so systematic
overconfidence silently disables the gate while every other metric still looks fine.

**Cost / latency** — p50/p95 reported. The v1 atoms are deterministic, so suite cost is
$0.00; when atoms take the LLM path this becomes the per-case cost line.

## Rules that keep the numbers honest

1. **Eval runs the production executor.** `evaluation/runner.py` calls the same
   `runtime/executor.py` the workflow uses. A separate evaluation path would measure code
   that never ships.
2. **No auto-approval during eval.** Gates are recorded as escalations and the case stops.
   Inventing a reviewer decision to "see what would have happened" inflates outcome
   accuracy with decisions no human made.
3. **Empty populations are `n/a`, never 0.0.** A category with no cases must not report a
   failure — otherwise a shrinking suite looks like a degrading system.
4. **Expectations encode a governance stance, and the stance is stated.** The runtime
   autonomously *rejects* only on unambiguous grounds (a hard sanctions match). Failed
   verification, tamper indicators and synthetic-identity signals escalate to a human —
   auto-rejecting those denies real customers on a model's say-so. Three golden cases were
   corrected to match this stance during Phase 6; the correction and its reasoning are in
   FAILURES.md rather than quietly applied.

## Delta detection (extraction-side)

Precision and recall against the frozen ledger in `data/interviews/SYNTHETIC.md`, targets
**≥ 0.7 / ≥ 0.7**. Scored by `extraction/delta_detect.py::score_against_ledger`. Misses and
false positives are analysed in FAILURES.md — a delta the system invents is as damaging as
one it misses, because both end up in front of a compliance officer.
