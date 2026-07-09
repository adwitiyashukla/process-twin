"""Retriever v1: vector search + cross-encoder rerank (brief §7.4).

The third leg — graph expansion (pull clauses already linked DERIVED_FROM the current
step, plus 1-hop neighbors) — lands in phase 3 once the graph exists. The seam is the
`extra_clause_ids` parameter, which the runtime will feed from Neo4j; "the graph tells
you where to look, the vectors tell you what's similar."
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from process_twin.retrieval.embedder import Embedder, Reranker


class RetrievedClause(BaseModel):
    model_config = ConfigDict(extra="forbid")

    clause_id: str
    text: str
    source_doc: str
    section_path: str
    vector_score: float | None = None  # None when injected via graph expansion
    rerank_score: float | None = None  # None when the reranker is unavailable


class Retriever:
    def __init__(
        self,
        client,
        collection: str,
        embedder: Embedder,
        reranker: Reranker | None,
        top_k: int,
        final_k: int,
    ) -> None:
        if final_k > top_k:
            raise ValueError(f"final_k ({final_k}) must be <= top_k ({top_k})")
        self._client = client
        self._collection = collection
        self._embedder = embedder
        self._reranker = reranker
        self._top_k = top_k
        self._final_k = final_k

    def search(
        self, query: str, extra_clause_ids: list[str] | None = None
    ) -> list[RetrievedClause]:
        """Vector top-k -> (optional) graph-injected extras -> rerank -> final-k."""
        vector = self._embedder.embed([query])[0]
        hits = self._client.query_points(
            collection_name=self._collection, query=vector, limit=self._top_k, with_payload=True
        ).points

        candidates = [
            RetrievedClause(
                clause_id=h.payload["clause_id"],
                text=h.payload["text"],
                source_doc=h.payload["source_doc"],
                section_path=h.payload["section_path"],
                vector_score=h.score,
            )
            for h in hits
        ]

        if extra_clause_ids:  # phase-3 graph expansion enters here
            present = {c.clause_id for c in candidates}
            extras = [cid for cid in extra_clause_ids if cid not in present]
            if extras:
                candidates.extend(self._fetch_by_ids(extras))

        if self._reranker is not None and candidates:
            scores = self._reranker.score(query, [c.text for c in candidates])
            for c, s in zip(candidates, scores, strict=True):
                c.rerank_score = float(s)
            candidates.sort(key=lambda c: c.rerank_score, reverse=True)
        else:
            candidates.sort(key=lambda c: (c.vector_score or 0.0), reverse=True)

        return candidates[: self._final_k]

    def _fetch_by_ids(self, clause_ids: list[str]) -> list[RetrievedClause]:
        from process_twin.retrieval.index import clause_point_id

        records = self._client.retrieve(
            collection_name=self._collection,
            ids=[clause_point_id(cid) for cid in clause_ids],
            with_payload=True,
        )
        return [
            RetrievedClause(
                clause_id=r.payload["clause_id"],
                text=r.payload["text"],
                source_doc=r.payload["source_doc"],
                section_path=r.payload["section_path"],
            )
            for r in records
        ]


def build_default_retriever(use_test_embedder: bool = False) -> Retriever:
    from qdrant_client import QdrantClient

    from process_twin.config import get_settings
    from process_twin.retrieval.embedder import get_embedder, get_reranker

    s = get_settings()
    return Retriever(
        client=QdrantClient(url=s.qdrant_url),
        collection=s.qdrant_collection,
        embedder=get_embedder(use_test_embedder),
        reranker=None if use_test_embedder else get_reranker(),
        top_k=s.retrieval_top_k,
        final_k=s.retrieval_final_k,
    )
