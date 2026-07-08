# Architecture decisions & trade-offs

Running decision log. Each entry: what was decided, what was rejected, and why — written
when the decision was made, not reconstructed later. The §12-mandated deep-dive writeups
(graph vs flat retrieval, compiled vs hand-written workflows, Delta nodes vs merge-averaging,
Temporal vs job queue, clause-ID stability, 10k-cases/day scaling) get their full sections
as their phases land.

## Phase 0

### Langfuse v2 (self-hosted) instead of v3
v3's self-host stack needs clickhouse + redis + minio + worker — six-plus containers on a dev
laptop, for zero additional benefit at our scale (traces, spans, generations, costs, eval scores
all exist in v2). The python SDK is pinned `<3` in pyproject.toml because the tracing wrapper
targets the v2 API. Revisit only if eval-score UX in v3 becomes compelling.

### Two postgres instances (temporal, langfuse) instead of one shared
Isolation of failure/restart/upgrade domains beats saving ~50MB idle RAM. `docker compose down`
on one subsystem can never corrupt the other's state, and either can be nuked independently
while debugging.

### Qdrant readiness checked host-side, not by container healthcheck
The qdrant image is distroless — no shell, no curl, so compose healthchecks can't run inside it.
`scripts/wait_healthy.py` (stdlib-only, so it works before `uv sync`) polls every service from
the host instead, and gives per-service diagnostics on timeout.

### Model tiering lives in config, not code
`MODEL_FAST` (Haiku-class) for bulk extraction and synthetic data; `MODEL_REASONING`
(Sonnet-class) for runtime decisions and reconciliation (ground rule 6). Pinned model strings so
eval numbers are reproducible; swapping tiers for cost/quality comparison is an env change,
which later gives the "extraction quality vs cost by tier" interview data point for free.

### Tracing is no-op-safe and lazily imported
Every tracing helper degrades to a no-op without Langfuse credentials. Tests, CI, and keyless
dev never fail because observability is unconfigured — and the same seam lets unit tests assert
tracing behavior without network. `import langfuse` happens only when keys exist.

### `--dry-run` is a first-class path, not a test hack
The hello atom (and later, every LLM-touching component) has a canned-response path. This is
what CI runs, and it is the seam phase-4 compiler tests will use to execute whole workflows
deterministically without a single API call.

### Strict schemas (`extra="forbid"`)
The self-correction loop (§6.1) works by feeding Pydantic's specific complaints back to the
model. A permissive schema would silently accept malformed output — the exact failure class
this project exists to catch.

## Phase 1

### Clause IDs are load-bearing (citation guardrail depends on them)
IDs like `CFR-1010.230(b)(1)` and `FFIEC-CDD-¶12` are derived from the *document structure*
(regulatory paragraph hierarchy / section paragraph index), never from chunk offsets. Re-running
ingestion on the same source bytes must yield byte-identical IDs — enforced by a determinism
test. Chunking for retrieval happens at clause granularity; oversized clauses split with
suffixed IDs (`…-¶3a`), keeping every citation human-checkable against the source.

### eCFR structured XML over PDF scraping for the CDD Rule
31 CFR 1010.230 is fetched from the eCFR versioner API **pinned to an as-of date** rather than
parsed out of a PDF. The paragraph hierarchy `(b)(1)(ii)` comes straight from the document
structure — stable IDs by construction instead of by regex heroics. FFIEC manual sections are
parsed from their HTML pages for the same reason. FATF R10 has no structured source, so its
interpretive-note paragraphs are the one place we parse PDF text.

### Data licensing split
FFIEC and CFR are US-government public domain → processed clauses are committed (reproducible
clone-and-run). FATF text is copyrighted → gitignored, regenerated locally via
`make fetch parse`; probe/eval cases that must always work cite CFR/FFIEC clauses.

### fastembed (ONNX) instead of sentence-transformers (torch)
BGE-small embeddings + BGE reranker via fastembed run on any CPU laptop with no torch install
(~2GB saved) and no API cost per embed. The embedder is behind a small protocol; tests use a
deterministic hashing embedder (clearly marked non-semantic) so retrieval *mechanics* are
unit-testable without model downloads; semantic quality is measured by the 20-probe acceptance
run (`make probe`), not by unit tests.

## Phase 2

### Synthetic corpus is authored + committed, generator is reproducibility tooling
Transcripts and case logs are committed artifacts generated once (method documented in
`data/interviews/SYNTHETIC.md`), not regenerated on every clone: delta-detection evaluation
needs a *frozen* ground truth, and regeneration drift would silently invalidate the ledger.
`scripts/generate_interviews.py --check` verifies the committed transcripts still voice every
ledger delta; case-log regeneration is seeded and byte-deterministic, enforced by test.

### Ground-truth labels live outside the data files
`cases.jsonl` contains nothing that names a delta; the delta tags live in a sidecar
(`ground_truth_tags.json`) used only by evaluation. If labels rode along inside the case
records, phase-3 extraction would be grading itself on leaked answers — the delta-detection
P/R numbers would be meaningless.
