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
