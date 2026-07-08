# Phase 0 review — scaffold, infra, config, tracing bootstrap

**Date:** 2026-07-08 · **Scope:** repo tree, pyproject (uv), docker-compose (neo4j, qdrant,
temporal+ui, langfuse), config, Makefile, CI, tracing bootstrap, hello-world atom.

## Acceptance criteria status

| Criterion | Status |
|---|---|
| `docker compose up` all healthy | ⚠️ compose + wait_healthy.py written; **must be run on the dev machine** (build sandbox has no docker). Run: `make up` |
| Hello-world atom runs, trace with cost in Langfuse | ⚠️ dry-run path verified end-to-end (schema-validated output, cost accounting, no-op tracing). Real-call trace needs `ANTHROPIC_API_KEY` + `make up`, then: `make hello` |
| `make test` green | ✅ 21 tests, plus ruff clean |

The two ⚠️ items are environment-bound, not code gaps; they are the first thing to verify
locally (5 minutes) and tick off here.

## Decisions made (details in docs/architecture.md)

Langfuse v2 over v3 (2 containers vs 6+ for identical value at our scale; SDK pinned `<3`);
two isolated postgres instances; host-side readiness script because qdrant's distroless image
can't self-healthcheck; model tiering + all guardrail thresholds in `config.py`, never inline;
tracing that no-ops without credentials and imports langfuse lazily; `--dry-run` as a
first-class seam (CI runs it; phase-4 compiler tests will reuse it); `extra="forbid"` on all
runtime schemas because the self-correction loop feeds Pydantic's complaints back to the model.

## Alternatives rejected

* **Langfuse v3 self-host** — clickhouse+redis+minio on a laptop buys nothing we use.
* **One shared postgres** — saves ~50MB RAM, couples restart/debug domains. Not worth it.
* **sentence-transformers for embeddings (phase 1)** — pulls torch (~2GB); fastembed's ONNX
  BGE models cover the same need on CPU. Declared as the `retrieval` extra already.
* **Auto-instrumented LLM calls** — Langfuse's anthropic wrapper hides token/cost plumbing;
  manual generation objects keep cost accounting explicit and testable (ground rule 6).

## Things Adi must be able to explain cold

1. **Why does tracing no-op instead of raising when keys are missing?** Observability must
   never be a hard dependency of correctness paths — CI and keyless dev still run the exact
   production code path, minus the export. The alternative (mocking Langfuse everywhere)
   tests the mock, not the seam.
2. **Why is `extra="forbid"` on every runtime schema?** The §6.1 self-correction loop
   re-prompts the model with the validation error text. Permissive schemas make bad output
   pass silently — you lose both the retry and the failure statistics.
3. **Why two model tiers in config?** Cost discipline (ground rule 6): bulk extraction is
   ~100x the call volume of runtime decisions. Pinned strings, not aliases, so eval numbers
   are reproducible; a tier swap is an env var, which later yields the quality-vs-cost
   comparison for free.
4. **Why is `--dry-run` not just a test fixture?** It is the seam that lets whole workflows
   execute deterministically without network — CI uses it today; the phase-4 compiler tests
   and phase-6 eval dry runs depend on the same seam. Design once, reuse three times.
5. **Walk through `make up`.** compose starts 7 containers; neo4j/postgres have container
   healthchecks; qdrant/langfuse/temporal-ui are polled host-side by wait_healthy.py
   (stdlib-only — it must run before `uv sync`); failure prints per-service diagnostics.

## Carry-forward

* Verify `make up` + `make hello` on the dev machine; attach the Langfuse trace screenshot
  to the README in phase 7 (§9 wants two screenshots).
* `uv lock` on the dev machine to commit the lockfile (sandbox lacks py3.11).
* FAILURES.md already has its first real entry (mount sync truncation during this build).
