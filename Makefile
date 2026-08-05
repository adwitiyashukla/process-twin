# process-twin — task runner.
# Windows note: run these from WSL2 (recommended, Docker Desktop integrates with it)
# or Git Bash with make installed. Every target is also a plain command you can copy.

.PHONY: up down nuke test verify lint fmt hello hello-dry fetch parse index probe seed diff api run-case worker replay determinism report demo-durability

up:            ## start neo4j, qdrant, temporal(+ui), langfuse; wait until all healthy
	docker compose up -d
	python scripts/wait_healthy.py

down:          ## stop services, keep data volumes
	docker compose down

nuke:          ## stop services AND delete all data volumes (fresh start)
	docker compose down -v

test:          ## run the test suite
	pytest

verify:        ## everything that runs without Docker or an API key
	ruff check .
	python scripts/check_determinism.py
	pytest
	python scripts/make_report.py

lint:          ## static checks (ruff)
	ruff check .

fmt:           ## auto-format
	ruff format .

hello:         ## phase 0 acceptance: run hello-world atom, trace + cost land in Langfuse
	python scripts/hello_atom.py

hello-dry:     ## same path without an API key or services (CI-safe)
	python scripts/hello_atom.py --dry-run

fetch:         ## phase 1: download policy corpus with pinned versions + checksums
	python scripts/fetch_policies.py

parse:         ## phase 1: raw policy docs -> clause-level JSONL with stable IDs
	python -m process_twin.ingestion.policy_pdf

index:         ## phase 1: build qdrant collection from processed clauses
	python -m process_twin.retrieval.index

probe:         ## phase 1 acceptance: 20 probe queries, hit@5 >= 0.9
	python scripts/probe_retrieval.py

seed:          ## phase 3: extraction -> reconcile -> delta detect -> graph load + acceptance
	python scripts/seed_graph.py

diff:          ## phase 3 / demo 1: tacit-vs-written diff as markdown
	python scripts/diff_report.py --format md

api:           ## serve approvals + explorer backend; explorer at :8000/explorer
	uvicorn process_twin.api.main:app --port 8000

# ---- phase-gated targets: fail loudly with a pointer, never silently no-op ----
run-case:      ## phase 4: run one golden case end to end (CASE=GC-003)
	python scripts/run_case.py --case $(CASE)

worker:        ## phase 5: start the Temporal worker
	python -m process_twin.durability.worker

replay:        ## phase 5: reconstruct a case from the audit log alone (CASE=GC-017)
	python scripts/replay_case.py $(CASE)

determinism:   ## phase 5: enforce the Temporal determinism rule
	python scripts/check_determinism.py
report:        ## phase 6 / demo 2: run the golden suite, emit the readiness report
	python scripts/make_report.py
demo-durability: ## phase 5: kill/restart worker, prove the case resumes
	bash scripts/demo_durability.sh $(CASE)
