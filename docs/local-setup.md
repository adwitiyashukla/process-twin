# Local first-run checklist (Adi's machine)

The build sandbox had no Docker and no route to the policy sites or model downloads, so
these verifications are environment-bound and run here. ~30 minutes total. Tick them off
in the phase-review docs as you go.

## 0. Prerequisites (once)

1. **WSL2 + Docker Desktop** (Settings → Resources → WSL integration ON). Work from a
   WSL shell for `make` targets. Check: `docker compose version && make --version`.
2. **uv**: `curl -LsSf https://astral.sh/uv/install.sh | sh` (inside WSL).
3. **Anthropic API key**: console.anthropic.com → API keys → create. Load a small credit
   (phases 3–6 bulk work runs on the Haiku tier; expect single-digit dollars total).
4. `cd process-twin && uv sync --all-extras && cp .env.example .env` — then put the key
   in `.env`. Also run `uv lock` once and commit `uv.lock`.

## 1. Phase-0 acceptance (needs Docker + key)

```bash
make up          # 7 containers; wait_healthy.py must print "All services healthy."
make test        # green, no key needed
make hello-dry   # works keyless
make hello       # REAL call: cost printed; open http://localhost:3000 (adi@local.dev /
                 # processtwin123) -> trace "case:CASE-HELLO" with cost attached
```

Tick the two ⚠️ rows in `docs/phase-reviews/phase-0.md`. Screenshot the trace (README
needs it in phase 7).

## 2. Phase-1 acceptance (needs network)

```bash
make fetch       # expect FFIEC slugs / FATF PDF path to possibly 404 — the script prints
                 # exactly what to do (--url-override); log any move in FAILURES.md
make parse       # eyeball per-source clause counts + first IDs; verify the FATF page
                 # range covers the R10 interpretive note in your downloaded edition
make index       # first run downloads BGE models (~400MB total), then indexes
make probe       # ACCEPTANCE: hit@5 >= 0.9. Record the number in phase-1.md.
```

Commit the CFR/FFIEC processed clauses (`git add data/policies/processed/*.jsonl` —
FATF ones are gitignored by design) and the updated `checksums.json`.

## 3. Phase-2 acceptance (no tools — you)

Read all 6 transcripts + `data/interviews/SYNTHETIC.md` line by line (the brief makes
your review the gate). You should be able to point at the exact sentences voicing each
of D1–D10, and at both sides of the D10 conflict.

## 4. Publish to GitHub

```bash
git status                    # should be clean; history has the per-phase commits
# create an EMPTY repo named process-twin on github.com (no README/license/gitignore)
git remote add origin https://github.com/<your-username>/process-twin.git
git push -u origin main       # CI (ruff + pytest) runs on push — should be green
```

If git ever complains about the repo state after the sandbox handoff, the full history
is also in `../process-twin-backup.bundle`:
`git clone process-twin-backup.bundle process-twin-restored`

## 5. Next Cowork session (Phase 3)

Open this folder in Cowork and start with: *"Read the build brief and
docs/phase-reviews/, then execute Phase 3 (extraction → reconciliation → delta
detection → graph load). My API key is in .env."* Phase 3 is the first LLM-heavy phase —
it needs the key and `make up` running, and its acceptance is delta-detection
P ≥ 0.7 / R ≥ 0.7 against the frozen ledger.
