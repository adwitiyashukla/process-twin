# RUN THIS — your execution checklist

Everything is built and committed. This is what only your machine can do. **~45 minutes**,
and you can push to GitHub after step 4 (steps 5–8 are then commits on top).

Delete this file before the final push (`git rm RUN-THIS.md`) — it's scaffolding, not part
of the project.

---

## 1. Prerequisites (~10 min)

```powershell
# Git — skip if `git --version` already works: https://git-scm.com/download/win
# uv (Python package manager):
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```
Close and reopen PowerShell after installing uv.

**Anthropic API key:** console.anthropic.com → sign in → *Billing* → add **$5** → *API Keys*
→ Create. Copy it. (Needed only for step 6; everything else runs without it.)

## 2. Install and configure (~5 min)

```powershell
cd C:\Users\HP\Documents\proj\process-twin
uv sync --all-extras
uv lock
copy .env.example .env
notepad .env      # paste your key after ANTHROPIC_API_KEY=  → save → close
```

## 3. Verify the whole thing offline (~2 min) ✅ *no Docker or key needed*

```powershell
uv run pytest                              # expect: 126 passed
uv run ruff check .                        # expect: All checks passed!
uv run python scripts/check_determinism.py # expect: determinism rule OK
uv run python scripts/make_report.py       # expect: VERDICT: GO
```
Then open `reports\<newest-folder>\report.html` in your browser. **That's Demo 2.**
📸 Screenshot it — the README references these numbers.

## 4. 🚀 Push to GitHub (~5 min) — do this now, not at the end

On github.com: **New repository** → name `process-twin` → **Public** → create it
**empty** (no README, no .gitignore, no licence).

```powershell
cd C:\Users\HP\Documents\proj\process-twin
git add -A
git commit -m "Phase 7: README with real evaluation numbers, demo script, phase reviews"
git remote add origin https://github.com/YOUR-USERNAME/process-twin.git
git branch -M main
git push -u origin main
```

Then on the repo page: ⚙️ *About* → description
`From written SOP to governed agent workflow — KYC process twin with policy-vs-practice delta detection, citation guardrails, durable execution, and pre-production evaluation.`
→ topics: `llm-agents` `langgraph` `neo4j` `graphrag` `temporal` `ai-governance` `regtech`.
Check the **Actions** tab — CI should go green.

**Your repo is live and interview-ready from here.** Everything below adds to it.

## 5. Start the services (~10 min, first run downloads ~3 GB)

```powershell
docker compose up -d
uv run python scripts/wait_healthy.py      # expect: All services healthy.
```
If a service is unhealthy: `docker compose ps` and `docker compose logs <service> --tail 50`.

```powershell
uv run python scripts/hello_atom.py        # real Haiku call, ~$0.001
```
Open http://localhost:3000 → log in `adi@local.dev` / `processtwin123` → find trace
**case:CASE-HELLO** with its cost. 📸 Screenshot for the README.

## 6. Build the real policy corpus (~10 min)

```powershell
uv run python scripts/fetch_policies.py
uv run python -m process_twin.ingestion.policy_pdf
uv run python -m process_twin.retrieval.index    # downloads ~400MB of BGE models
uv run python scripts/probe_retrieval.py         # ACCEPTANCE: hit@5 >= 0.9
```
If `fetch_policies` prints `[FAIL]` for a source, the page moved — the script tells you
exactly what to do (`--url-override name=<new-url>`). Note the move in FAILURES.md.

Record your hit@5 number in `docs/phase-reviews/phase-1.md`, then commit the corpus:
```powershell
git add data/policies/processed/cfr_*.jsonl data/policies/processed/ffiec_*.jsonl data/policies/raw/checksums.json
git commit -m "Phase 1: real policy corpus, hit@5 = <your number>"
```

## 7. Seed the process twin (~5 min, uses the API key)

```powershell
uv run python scripts/seed_graph.py       # prints delta P/R + provenance coverage
uv run python scripts/diff_report.py --format md --out docs/diff-report.md
```
Then `uv run uvicorn process_twin.api.main:app --port 8000` and open
http://localhost:8000/explorer — toggle **diff mode**, click a delta. **That's Demo 1.**
📸 Screenshot.

Record the real delta P/R in `docs/phase-reviews/phase-3.md`, commit:
```powershell
git add -A
git commit -m "Phase 3: seeded process twin, delta detection P=<x> R=<y>"
```

## 8. Durability demo (~5 min) — needs WSL or Git Bash

```bash
cd /mnt/c/Users/HP/Documents/proj/process-twin
bash scripts/demo_durability.sh GC-037
```
Expect: `DEMO PASSED: case resumed after worker kill, audit trail intact`. Run it three
times (that's the Phase 5 acceptance). 🎥 Screen-record one run for the demo video.

## 9. Finish

```powershell
git rm RUN-THIS.md
git add -A
git commit -m "docs: local acceptance results recorded"
git push
```

Optional, high leverage for recruiters: record the 3-minute video from
`docs/demo-script.md`, upload it unlisted to YouTube, and put the link at the top of the
README.

---

## If something breaks

Paste me the exact command and its full output. Most likely issues, all handled:

- **`fetch_policies` 404** → the page moved; use `--url-override` as the script prints.
- **`docker compose up` port conflict** → something else is on 3000/7474/7687/6333/7233/8233.
  `docker compose down`, free the port, retry.
- **`make` not found** → you're in PowerShell; every Makefile target is also a plain
  `uv run python …` command (this checklist uses those).
- **Langfuse login fails** → the headless bootstrap didn't run for your image version; sign
  up in the UI, create a project, paste its keys into `.env`.

## Before the interview

Read `docs/phase-reviews/` end to end — the "explain cold" sections are your prep. The five
strongest talking points: the `(h)→(i)` clause-ID ambiguity, why conflicts become `Delta`
nodes instead of being averaged, why LLM calls can't live in Temporal workflow code, the
citation guardrail's two failure modes, and the 0.85-vs-1.0 threshold asymmetry.
