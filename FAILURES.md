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
