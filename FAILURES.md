# FAILURES.md — running log of everything that broke

First-class artifact per ground rule 4. Every schema validation failure, extraction miss,
retrieval whiff, infra gotcha: date, what broke, how it was detected, the fix, the prevention.
If this file is short at the end, something was hidden.

Entry format:

```
## YYYY-MM-DD — <one-line title>
**What broke:**
**How it was detected:** (test? trace? eval regression? manual run?)
**Fix:**
**Prevention:**
```

---

## 2026-07-08 — Host↔sandbox file mount pinned edited files at stale byte length
**What broke:** Three source files edited after creation appeared truncated (cut mid-token at
their pre-edit byte size) when read through the build sandbox's mount, breaking ruff/pytest
runs with bogus syntax errors — while the host copies were verifiably complete.
**How it was detected:** `ruff` reported `F821 Undefined name 'Fa'` — the tail of
`_client_initialized = False` cut at exactly the file's previous size. `wc -c` on both sides
of the mount confirmed content synced but length didn't.
**Fix:** Rewrote the affected files from the sandbox side (full-content heredoc), which
write-back-synced to the host correctly; adopted "create via host tools, modify via
sandbox-side full rewrite" for the rest of the session.
**Prevention:** Verification runs now start with an `ast.parse` / `wc -c` sanity pass over
edited files before interpreting any lint/test failure as real.

## 2026-07-08 — D5 case-log tags had no evidence in the case records
**What broke:** Two tacit cases (T5, T12) carried D5 in the ground-truth sidecar, but the
generator never wrote the D5 evidence (fresher-document note) into their records — the
sidecar promised support the data couldn't show. The phase-3 pattern miner found 4
supporting cases where the ledger claimed 6.
**How it was detected:** Designing the miner↔ledger lockstep test: mining cases.jsonl
alone (no sidecar) must reproduce every ledger support count. D5 came up short.
**Fix:** Added the missing D5 branch to `build_tacit`; regenerated the committed corpus.
**Prevention:** `test_miner_supports_match_ledger` now enforces that every ledger count is
recoverable from the raw case records — tags without evidence can no longer hide.

## 2026-08-04 — Delta rules fired on error cases before trigger+response pairing
**What broke:** Early pattern predicates matched on the trigger alone (e.g. "two address
mismatches present"), so genuine-error case HC-059 — mismatches noted, no referral made —
counted as support for the D3 tacit pattern. A mistake was being sold as a practice.
**How it was detected:** `test_error_cases_do_not_leak_into_pattern_support`, written
deliberately against the near-delta error cases seeded in phase 2.
**Fix:** Every tacit-pattern predicate now requires BOTH the trigger and the practiced
response (mismatch AND referral; callback skipped AND activity under the $10k band).
**Prevention:** The error-leak test is permanent; new patterns must state their response
condition, and phase-2 keeps near-delta error cases as standing precision traps.

## 2026-08-04 — Determinism checker flagged its own docstring
**What broke:** `scripts/check_determinism.py` (regex over raw file text) reported
`workflows.py` as violating the Temporal determinism rule. The "violation" was the
sentence in the module docstring stating that the module contains no `datetime.now()`
calls — documenting the rule broke the rule's own check, and any explanatory comment
would have done the same.
**How it was detected:** First run of the new check, immediately after writing the
workflow module — the reported line pointed at prose, not code.
**Fix:** Rewrote the checker to parse the AST and inspect call targets only, so it
verifies what the code *does* rather than what it *says*. Error output now names the
line number and the reason, and points at activities.py as the fix.
**Prevention:** Lint-style guards over source must analyze structure, not text. Same
lesson applies to the citation guardrail: existence checks on a string are weaker than
checks on meaning, which is exactly why that guardrail also reranks for relevance.

## 2026-08-04 — Guardrail ordering hid the atom's real escalation reason
**What broke:** A beneficial-ownership boundary case (owner at 22% in a high-risk
jurisdiction) escalated with the reason "confidence 0.50 < 0.7". True, but useless to a
reviewer: the atom had a precise explanation — the case sits between the written 25% rule
and the practised 20% threshold — and the generic confidence gate fired first and won.
**How it was detected:** `test_boundary_case_escalates_and_never_auto_decides` asserted
the reason mentioned the unresolved threshold and failed on the confidence string.
**Fix:** Reordered `run_all` by how FUNDAMENTAL each problem is: delta guard → citation
validity → the atom's own `needs_human` note → confidence gate as the catch-all. Low
confidence is usually the *symptom* of the atom encoding an unresolved question, so the
atom's note outranks it.
**Prevention:** The ordering and its rationale are documented in the function docstring,
and the boundary test asserts on the reason text, not just the fact of escalation.

## 2026-08-05 — Two written EDD triggers were folded into the risk score and vanished
**What broke:** GC-026 (beneficial owner at 30% in a high-risk jurisdiction) and GC-027
(four owners across four jurisdictions) were both APPROVED straight through. Both are
written EDD triggers. They had been implemented as *contributions to an additive risk
score*, and both landed at "medium" — below the score threshold that triggers EDD.
**How it was detected:** First full golden-suite run: outcome accuracy 0.725, with those
two cases in the failure list. Not caught earlier because the unit tests exercised the
atoms individually, where each returned a defensible-looking risk score.
**Fix:** `determine_edd_requirement` now evaluates written triggers DIRECTLY against the
applicant (owner ≥25% in a high-risk jurisdiction; complex multi-jurisdiction ownership)
instead of inferring them from an aggregate score. Scores rank risk; they must not be the
only route by which a categorical policy rule fires.
**Prevention:** Golden-suite cases exist for both triggers, and the rule is stated in the
atom: a written trigger is a predicate over the case, never a threshold on a score.

## 2026-08-05 — Path-fidelity metric punished correct escalations
**What broke:** Path fidelity read 0.00 and then 0.65. The metric demanded every expected
step execute, so any case that correctly halted at a human gate scored as a path failure —
and the compiled workflow's extra steps (the callback control runs for all applicants;
beneficial-ownership runs for individuals and returns "not applicable") also counted
against cases that never listed them.
**How it was detected:** 14 path failures on cases whose outcomes were all correct — a
metric disagreeing with every other signal is usually the thing that's wrong.
**Fix:** Redefined path fidelity: project the actual path onto the expected step set, then
require exact equality for completed cases and an in-order PREFIX for cases that stopped
early. Skips and reordering still fail; halting correctly and running extra steps do not.
**Prevention:** Six unit tests pin the definition. The deeper lesson is in the docstring
and eval-methodology.md: a metric that penalises correct escalation would, if optimised
against, tune the whole system toward straight-through processing — the exact opposite of
what a governance system is for.

## 2026-08-05 — Metrics with an empty population reported 0.0 and failed the run
**What broke:** A suite subset containing no adversarial cases produced
`escalation_recall_adversarial = 0/0 = 0.0`, which failed its 0.83 threshold and turned a
passing run into NO-GO.
**How it was detected:** `test_caught_policy_conflict_allows_go` used a small synthetic
eval set and got NO-GO for a category it never contained.
**Fix:** `compute_metrics` takes an explicit population size; an empty population yields
`passed=None` and is reported as "n/a" rather than as a failure.
**Prevention:** Division-by-zero in a metric is never zero — it is "not measured". A
shrinking suite must not look like a degrading system.

## 2026-08-05 — Three golden cases encoded the wrong governance stance
**What broke:** GC-020 (no primary identity document), GC-032 (synthetic-identity signals)
and GC-033 (document-tamper indicators) expected `rejected`. The runtime escalated all
three to a human instead, and was marked wrong.
**How it was detected:** Full golden-suite run; all three failures shared a shape — the
system escalating where the suite wanted an autonomous rejection.
**Fix:** The expectations were wrong, not the system, so they were corrected — and the
stance behind them is now written down: **the runtime autonomously rejects only on
unambiguous grounds (a hard sanctions match); everything else that fails verification goes
to a human.** Auto-rejecting on tamper heuristics denies real customers on a model's
say-so, and every one of those signals has a false-positive rate.
**Prevention:** The stance is stated in docs/eval-methodology.md as a numbered rule, so
future cases are written against a policy rather than an intuition. Recording it here
rather than silently editing the YAML is the point: changing an expectation to make a test
pass is only legitimate when the reasoning survives being written down.

## 2026-08-05 — Publish script reported "lint and tests green" for checks that never ran
**What broke:** `publish.ps1` guards publication behind `uv run ruff check` and
`uv run pytest`. On a machine without `uv`, PowerShell raised CommandNotFoundException for
both; `$LASTEXITCODE` retained its stale value from the previous successful command, so
both `-ne 0` guards passed and the script printed "lint and tests green." The project was
published with a verification step that had silently not executed.
**How it was detected:** Reading the actual console output rather than the summary line —
the CommandNotFoundException was visible directly above the green "lint and tests green."
GitHub Actions independently confirmed the code itself was fine, but that was luck, not
the guard working.
**Fix:** The step now checks `Get-Command uv` first. If the tool is absent it says so
loudly, states that the checks did NOT run, and points at the Actions tab — it never
claims a pass it didn't observe.
**Prevention:** A check must distinguish three states, not two: passed, failed, and
*did not run*. Conflating the third with the first produces false confidence, which is
strictly worse than no check at all. This is the same failure mode the project's own
metrics guard against (FAILURES.md 2026-08-05: empty populations reported 0.0) and the
same reason CI runs on a clean runner rather than trusting a developer machine.

## 2026-08-05 — "Byte-identical regeneration" held only on Linux
**What broke:** `test_committed_cases_match_regeneration_byte_for_byte` failed on Windows:
`ground_truth_tags.json drifted from its generator`, diff at index 1, `b'\n' != b'\r'`.
The generator wrote `cases.jsonl` through an explicit `open(..., newline="\n")` but wrote
the two JSON sidecars via `Path.write_text()`, which applies the platform line-ending
default. On Windows those files gained CRLF, so the reproducibility guarantee the README
makes — and that the frozen delta ledger depends on — was true on Linux and false on
Windows. Every CI run was green because CI runs Ubuntu.
**How it was detected:** First execution of the suite on a Windows machine, minutes after
the project was published. Nine phases of green CI never touched this, because the CI
runner and the development sandbox were both Linux.
**Fix:** Every artifact write in the generator now pins `newline="\n"` explicitly.
**Prevention:** A determinism claim is only as strong as the platforms it was checked on.
Single-OS CI cannot verify cross-platform reproducibility — the honest options are a test
matrix (ubuntu + windows) or scoping the claim to one platform. Added to the roadmap;
until then the claim is exercised on both by virtue of local runs on Windows.
