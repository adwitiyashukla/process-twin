# Phase 1 review — policy ingestion, clause store, retriever v1

**Date:** 2026-07-08 · **Scope:** fetch with pinned versions + checksums, clause-level
parsing with stable IDs, qdrant index, vector+rerank retriever, 20-probe acceptance suite.

## Acceptance criteria status

| Criterion | Status |
|---|---|
| 20 probe queries hit@5 ≥ 0.9 | ⚠️ suite + runner ready (`make probe`); **needs the real corpus on the dev machine** — the build sandbox could reach neither the policy sites nor HuggingFace model downloads. Run: `make fetch parse index probe` |
| Clause IDs stable across re-runs | ✅ byte-identical re-parse proven by test (`test_reparse_is_byte_identical`), incl. checksums |

Also verified: 37 unit tests green (parser hierarchy/ambiguity/splitting/dedupe, retrieval
mechanics on in-memory qdrant, k-limits, graph-injection seam), ruff clean.

## Decisions made (details in docs/architecture.md → Phase 1)

eCFR versioner XML pinned to an as-of date instead of PDF scraping (IDs from document
structure by construction); FFIEC from HTML pages; FATF is the only true PDF parse and its
¶ IDs use the note's own printed numbers so a shifted page range never renumbers existing
clauses; clause-granularity chunking with deterministic suffixed splits (…¶3a); public-domain
clauses (CFR/FFIEC) committed, FATF regenerated locally (licensing); fastembed/BGE over
torch-based sentence-transformers; a TEST-ONLY hashing embedder so mechanics are testable
offline; probes assert clause-ID *prefixes* so they're robust to paragraph numbering while
still catching wrong-document retrieval.

## Alternatives rejected

* **Fixed-size token chunking** — destroys citation checkability; a chunk is not a clause.
* **Exact expected IDs in probes** — brittle against upstream renumbering; prefixes keep the
  acceptance meaningful without hand-maintenance.
* **Letting the reranker be mandatory** — a missing model download would hard-fail the whole
  pipeline; instead it degrades loudly to vector order (and `--no-rerank` doubles as ablation).

## The (h)→(i) story — know this cold

CFR paragraph markers are ambiguous: `(i)` is both the letter after `(h)` and roman one.
31 CFR 1010.230 genuinely has paragraphs (a)–(j), so naive roman detection corrupts IDs
mid-document. Rule implemented: letter-sequence continuation beats the roman reading;
romans are only accepted while a numbered level is open. `test_letter_i_after_h_is_letter_not_roman`
pins it. This is the concrete example of why "stable IDs" is an engineering problem, not a slogan.

## Things Adi must be able to explain cold

1. Why clause-stable IDs are load-bearing (citation guardrail §7.3 + `must_cite` evals
   compare strings; silent re-pointing = silently wrong audits).
2. The (h)→(i) ambiguity and the continuation-beats-roman rule.
3. Why probes use prefix matching and what failure it still catches.
4. Why the hashing embedder exists and why it must never serve production traffic
   (lexical trigram overlap ≠ semantics; it tests plumbing, `make probe` tests quality).
5. The licensing split: why FATF clauses are gitignored while CFR/FFIEC are committed.

## Carry-forward (first local session)

1. `make fetch` — expect FFIEC slugs or the FATF PDF path to need `--url-override`
   (documented in the script docstring); log any move in FAILURES.md.
2. `make parse` — eyeball printed per-source clause counts + first IDs; verify FATF page
   range covers the R10 interpretive note in the downloaded edition.
3. `make index && make probe` — record hit@5 + MRR here and in FAILURES.md if any probe
   misses systematically. Commit `data/policies/processed/cfr_*.jsonl` + `ffiec_*.jsonl`.
