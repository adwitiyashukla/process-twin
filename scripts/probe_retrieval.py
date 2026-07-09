"""Phase-1 acceptance: 20 probe queries against the real corpus, hit@5 >= 0.9.

    make probe                    # requires: make up && make fetch parse index
    python scripts/probe_retrieval.py --no-rerank   # ablation: vector-only comparison

Reports hit@5 and MRR per probe and overall. Failing probes print what WAS retrieved —
that diff is the debugging surface (and FAILURES.md material when systematic).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

PASS_THRESHOLD = 0.9  # brief §13 phase-1 acceptance


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-rerank", action="store_true", help="vector-only ablation")
    parser.add_argument("--probes", default="data/policies/probes.yaml")
    args = parser.parse_args()

    from process_twin.retrieval.retriever import build_default_retriever

    retriever = build_default_retriever()
    if args.no_rerank:
        retriever._reranker = None  # ablation switch, test-visible on purpose

    spec = yaml.safe_load(Path(args.probes).read_text(encoding="utf-8"))
    hits, rr_sum, failures = 0, 0.0, []

    for probe in spec["probes"]:
        results = retriever.search(probe["query"])
        ids = [r.clause_id for r in results]
        rank = next(
            (
                i + 1
                for i, cid in enumerate(ids)
                if any(cid.startswith(p) for p in probe["expected_prefixes"])
            ),
            None,
        )
        if rank is not None:
            hits += 1
            rr_sum += 1.0 / rank
            print(f"  [hit @{rank}] {probe['id']}: {probe['query'][:60]}…")
        else:
            failures.append((probe, ids))
            print(f"  [MISS]    {probe['id']}: {probe['query'][:60]}…")
            for cid in ids:
                print(f"            got: {cid}")

    n = len(spec["probes"])
    hit_at_5 = hits / n
    mrr = rr_sum / n
    print(f"\nhit@5 = {hit_at_5:.2f} ({hits}/{n})   MRR = {mrr:.3f}   "
          f"threshold = {PASS_THRESHOLD} -> {'PASS' if hit_at_5 >= PASS_THRESHOLD else 'FAIL'}")
    if failures:
        print(f"{len(failures)} miss(es): analyze, then log systematic ones in FAILURES.md.")
    return 0 if hit_at_5 >= PASS_THRESHOLD else 1


if __name__ == "__main__":
    sys.exit(main())
