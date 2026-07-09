# SYNTHETIC.md — generation method + ground-truth delta ledger

**Everything under `data/interviews/transcripts/` and `data/case_logs/` is synthetic.**
No real customers, employees, institutions, or cases. This file is the honest record the
README links to (ground rule 3), and the ledger below is the *evaluation ground truth*
for delta detection (brief §6.3): detected deltas are scored against this table
(target precision ≥ 0.7, recall ≥ 0.7).

## How the data was generated

* **Transcripts** were authored by Claude (the build assistant) during the phase-2 Cowork
  session: one pass per persona, given `personas.yaml`, the interview guide, and that
  persona's assigned deltas, with instructions to voice each delta *naturally* amid
  ordinary policy-consistent process talk and deliberate red herrings (tooling gripes,
  staffing complaints — things that sound like deltas but aren't process divergences).
  The corpus is **committed and frozen**: delta-detection evaluation needs a fixed ground
  truth, and regenerating on every clone would silently invalidate the ledger.
  `scripts/generate_interviews.py` documents the prompts and provides `--check`, which
  verifies every ledger delta is still voiced verbatim-or-near in its assigned transcripts.
* **Case logs** are produced by `scripts/generate_case_logs.py` — deterministic templates,
  no randomness, no LLM — so `make` on any machine regenerates byte-identical files
  (enforced by test). Distribution per brief §4.3: **35 policy-consistent / 18 tacit-pattern
  / 7 genuine-error** cases.
* **Ground-truth labels live in a sidecar** (`data/case_logs/ground_truth_tags.json`), never
  inside `cases.jsonl` itself: the phase-3 extractor must mine patterns from what a real
  bank would have (case records), not from leaked answer keys. Same reason the transcripts
  never name delta IDs.
* **Jurisdictions:** low-risk jurisdictions are real (US, UK, Canada, Germany, Japan);
  high-risk jurisdictions are fictional (Kavastan, Zubaria, Port Meridian) so the synthetic
  corpus never couples to live FATF list churn and never mislabels a real country.
* **Error cases (E1–E7) are not delta-tagged.** A pattern needs support; a one-off mistake
  is noise. The detector should *not* report E-group behaviors as deltas — doing so counts
  against precision. (E5/E6 are near-delta topics on purpose: they skip controls *outside*
  the tacit thresholds, exactly the confusion a lazy detector falls into.)

## Why authored synthetic data doesn't invalidate the evaluation

The evaluation measures whether the *pipeline* (extraction → reconciliation → delta
detection) recovers divergences that verifiably exist in its inputs — the ledger defines
existence. What it does NOT measure is performance on organic human speech; that
limitation is stated in the README. What *would* invalidate it: labels leaking into
extractor inputs, deltas "voiced" only as paraphrases of the ledger text (we voice them
as workplace anecdotes instead), or tuning the detector against this ledger and reporting
the same numbers (phase 6 keeps extraction-side eval separate from tuning runs).

## Delta ledger (ground truth)

Written positions cite clause families; exact ¶-level IDs get pinned when phase 3 links
evidence to the fetched corpus (FFIEC ¶ numbering exists only after `make fetch parse`).

| ID | Kind | Sev | Written position | Practiced position | Voiced by | Log support |
|----|------|-----|------------------|--------------------|-----------|-------------|
| D1 | threshold divergence | high | 25% beneficial-ownership identification threshold — CFR-1010.230(b) family | Analysts apply extra scrutiny + EDD referral from **20%** for high-risk-jurisdiction owners | P1, P3 | 11 |
| D2 | undocumented acceptance | medium | Manual silent on expired primary ID — FFIEC-CIP (documentary verification) | **Expired passport + official renewal receipt accepted**, with a 30-day follow-up task | P4, P6 | 5 |
| D3 | unwritten rule | medium | No such trigger anywhere in policy | **Two address mismatches across documents → automatic EDD referral** | P4, P5 | 5 |
| D4 | sequence divergence | low | Policy implies identity verification precedes screening — FFIEC-CIP/CDD ordering | **Sanctions/PEP screening runs first** to fail fast and save verification effort | P1, P6 | 8 |
| D5 | stricter practice | low | Utility bill acceptable up to 90 days — FFIEC-CIP (address verification) | Senior analysts only accept **≤ 60 days** | P1, P2 | 6 |
| D6 | skipped step | high | Written callback verification for phone numbers — FFIEC-CIP (non-documentary) | **Skipped for accounts under $10k expected activity** | P2, P4, P6 | 6 |
| D7 | informal escalation | medium | PEP-associate cases go to formal EDD ticket — FFIEC-CDD (EDD triggers) | **Verbal walk-over to the compliance officer first**; ticket filed only after that chat | P3, P5 | 3 |
| D8 | tooling workaround | high | Name screening at standard match tolerance — FFIEC-CIP/CDD (screening) | **Match tolerance manually widened for transliterated (non-Latin-origin) names** | P1, P5 | 4 |
| D9 | gap | medium | No written guidance for foreign-tax-ID-only applicants | **Ad hoc EDD-specialist review** decides case by case | P3, P5 | 3 |
| D10 | practitioner conflict | medium | PO-box addresses: policy names no explicit rule — FFIEC-CIP (address) | **QA rejects outright** (P2) vs **frontline accepts with one extra document** (P4) — conflict *between practitioners* | P2 ⟂ P4 | 4 (2 reject / 2 accept) |

Severity rubric (brief §6.3): regulatory exposure > customer impact > efficiency.
D1/D6/D8 are high — undocumented deviation on a certified threshold, a skipped verification
control, and a widened screening tolerance are exactly what an examiner writes up.

## Recommendations (what the diff demo shows per delta)

D1 encode-exception (document the 20% high-risk practice, or align to 25% and retrain) ·
D2 align-policy (codify the renewal-receipt acceptance + follow-up task) · D3 encode-exception
(the trigger is good control design — write it down) · D4 align-policy (screening-first is
defensible; update the written order) · D5 retrain-or-align (pick one number) · D6 **retrain
staff** (a control is being skipped on an invented threshold) · D7 retrain (formal ticket
first, chat second) · D8 **fix tooling** (transliteration handling belongs in the matcher,
not in a manual tolerance override) · D9 align-policy (write the foreign-tax-ID procedure)
· D10 align-policy (pick a rule; two customers, two outcomes is indefensible).
