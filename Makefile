# process-twin — task runner.
# Windows note: run these from WSL2 (recommended, Docker Desktop integrates with it)
# or Git Bash with make installed. Every target is also a plain command you can copy.

.PHONY: up down nuke test lint fmt hello hello-dry fetch parse index probe seed run-case report demo-durability

up:            ## start neo4j, qdrant, temporal(+ui), langfuse; wait until all healthy
	docker compose up -d
	python scripts/wait_healthy.py

down:          ## stop services, keep data volumes
	docker compose down

nuke:          ## stop services AND delete all data volumes (fresh start)
	docker compose down -v

test:          ## run the test suite
	pytest

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

# ---- phase-gated targets: fail loudly with a pointer, never silently no-op ----
seed:
	@echo "make seed arrives in Phase 3 (extraction -> reconcile -> graph load)"; exit 1
run-case:
	@echo "make run-case arrives in Phase 4 (compiler + atoms + guardrails + HITL)"; exit 1
report:
	@echo "make report arrives in Phase 6 (golden suite + readiness report)"; exit 1
demo-durability:
	@echo "make demo-durability arrives in Phase 5 (temporal kill/restart demo)"; exit 1
