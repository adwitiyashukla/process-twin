"""Phase-3 orchestrator: ingestion -> extraction -> reconcile -> delta detect -> Neo4j."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, "src")

from process_twin.config import get_settings  # noqa: E402
from process_twin.extraction.delta_detect import detect_deltas, score_against_ledger  # noqa: E402
from process_twin.extraction.extractor import default_model_call, extract_source  # noqa: E402
from process_twin.extraction.reconcile import llm_adjudicator, reconcile  # noqa: E402
from process_twin.graph.loader import load_graph  # noqa: E402
from process_twin.graph.queries import ALL_DELTAS, PROVENANCE_COVERAGE  # noqa: E402
from process_twin.ingestion.case_logs import load_cases, mine_patterns  # noqa: E402
from process_twin.ingestion.policy_pdf import read_clauses_jsonl  # noqa: E402
from process_twin.ingestion.transcripts import load_all_transcripts  # noqa: E402
from process_twin.observability import tracing  # noqa: E402

DERIVED = Path("data/derived")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-graph", action="store_true", help="run pipeline, skip Neo4j load")
    ap.add_argument("--force-extract", action="store_true")
    ap.add_argument("--test-embedder", action="store_true", help="offline hashing embedder")
    ap.add_argument("--model-tier", choices=["fast", "reasoning"], default="fast")
    args = ap.parse_args()
    settings = get_settings()

    processed = Path("data/policies/processed")
    clause_files = sorted(processed.glob("*.jsonl"))
    if not clause_files:
        print("No processed clauses found - run `make fetch` then `make parse` first.")
        return 1
    clauses = [c for f in clause_files for c in read_clauses_jsonl(f)]
    segments = load_all_transcripts()
    cases = load_cases()
    patterns = mine_patterns(cases)
    print(f"sources: {len(clauses)} clauses, {len(segments)} interview segments, "
          f"{len(cases)} cases -> {len(patterns)} mined patterns")

    if not settings.anthropic_api_key and not args.force_extract:
        cache_ok = all((Path("data/extracted") / f"{n}.jsonl").exists()
                       for n in ("policy", "interviews", "case_patterns"))
        if not cache_ok:
            print("No ANTHROPIC_API_KEY and no extraction cache - add the key to .env first.")
            return 1

    trace = tracing.start_case_trace("SEED", phase="3", model_tier=args.model_tier)
    policy_items = [(c.clause_id, c.text) for c in clauses]
    interview_items = [
        (s.id, f"[{s.persona_name}, asked: {s.question}] {s.text}") for s in segments
    ]
    pattern_items = []
    case_by_id = {c.case_id: c for c in cases}
    for p in patterns:
        examples = " | ".join(
            case_by_id[cid].analyst_notes[:200] for cid in p.case_ids[:2] if cid in case_by_id
        )
        pattern_items.append(
            (p.id, f"Observed in {p.support_count}/60 historical cases: "
                   f"{p.pattern_description}. Example analyst notes: {examples}")
        )

    kw = {"model_tier": args.model_tier, "force": args.force_extract, "trace": trace}
    elements = (
        extract_source("policy", policy_items, "policy", **kw)
        + extract_source("interviews", interview_items, "interview", **kw)
        + extract_source("case_patterns", pattern_items, "case_log", **kw)
    )
    print(f"extraction: {len(elements)} elements "
          f"(cache: data/extracted/, dead letters: data/dead_letter/)")

    from process_twin.retrieval.embedder import get_embedder

    embedder = get_embedder(use_test_embedder=args.test_embedder)
    adjudicate = None
    if settings.anthropic_api_key and not args.test_embedder:
        adjudicate = llm_adjudicator(default_model_call(settings.model_reasoning))
    canonicals, conflicts = reconcile(elements, embedder, adjudicate)
    print(f"reconcile: {len(canonicals)} canonical elements, {len(conflicts)} conflicts")

    deltas = detect_deltas(canonicals, conflicts, patterns)
    score = score_against_ledger(deltas)
    print(f"deltas: {len(deltas)} detected")
    print(f"  P = {score['precision']:.2f}  R = {score['recall']:.2f}  "
          f"(target >= 0.70 / >= 0.70)  missed: {score['missed_rows'] or 'none'}")
    if score["missed_rows"] or score["precision"] < 0.7:
        print("  -> analyze misses/false positives in FAILURES.md (ground rule 4)")

    DERIVED.mkdir(parents=True, exist_ok=True)
    dumps = {
        "canonicals.json": [c.model_dump() for c in canonicals],
        "conflicts.json": [c.model_dump() for c in conflicts],
        "deltas.json": [d.model_dump() for d in deltas],
        "patterns.json": [p.model_dump() for p in patterns],
        "ledger_score.json": score,
    }
    for name, payload in dumps.items():
        (DERIVED / name).write_text(
            json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    print(f"derived artifacts -> {DERIVED}/")

    if args.skip_graph:
        tracing.flush()
        print("(--skip-graph: Neo4j load skipped)")
        return 0
    from neo4j import GraphDatabase

    clause_meta = [{"clause_id": c.clause_id, "source_doc": c.source_doc,
                    "section_path": c.section_path, "checksum": c.checksum} for c in clauses]
    driver = GraphDatabase.driver(settings.neo4j_uri,
                                  auth=(settings.neo4j_user, settings.neo4j_password))
    with driver.session() as session:
        stats = load_graph(session, canonicals, deltas, segments, patterns, clause_meta)
        cov = session.run(PROVENANCE_COVERAGE).single()
        sample = [r["id"] for r in session.run(ALL_DELTAS)][:5]
    driver.close()
    tracing.flush()

    print(f"graph: {stats}")
    print(f"provenance coverage: {cov['elements']} elements, {cov['orphans']} orphans "
          f"{'PASS' if cov['orphans'] == 0 else 'FAIL - investigate before proceeding'}")
    print(f"delta sample: {sample}")
    print("explorer: make api  ->  http://localhost:8000/explorer")
    return 0 if cov["orphans"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
