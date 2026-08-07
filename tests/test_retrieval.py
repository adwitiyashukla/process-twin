"""Retrieval mechanics against an in-memory qdrant with the deterministic hashing"""

import pytest

from process_twin.ingestion.policy_pdf import make_record
from process_twin.retrieval.embedder import HashingEmbedder
from process_twin.retrieval.index import clause_point_id, index_clauses
from process_twin.retrieval.retriever import Retriever

CLAUSES = [
    ("CFR-1010.999(a)", "Beneficial ownership threshold of twenty five percent equity."),
    ("CFR-1010.999(b)", "Certification form must be obtained at account opening."),
    ("FFIEC-CIP-¶1", "Customer identification program collects name date of birth and address."),
    ("FFIEC-CIP-¶2", "Documentary verification uses unexpired government issued identification."),
    ("FFIEC-CDD-¶1", "Ongoing customer due diligence updates the customer risk profile."),
    ("FFIEC-CDD-¶2", "Enhanced due diligence applies to higher risk customer relationships."),
    ("FATF-R10-IN-¶7", "Timing of verification may follow establishment of the relationship."),
    ("FATF-R10-IN-¶9", "Simplified measures are acceptable in lower risk situations."),
]


@pytest.fixture(scope="module")
def indexed_client():
    qdrant_client = pytest.importorskip("qdrant_client")
    client = qdrant_client.QdrantClient(":memory:")
    records = [make_record(cid, "doc", "sec", text) for cid, text in CLAUSES]
    n = index_clauses(client, "test_clauses", records, HashingEmbedder())
    assert n == len(CLAUSES)
    return client


def _retriever(client, final_k=5, reranker=None):
    return Retriever(
        client=client, collection="test_clauses", embedder=HashingEmbedder(),
        reranker=reranker, top_k=8, final_k=final_k,
    )


def test_lexical_query_finds_its_clause(indexed_client):
    hits = _retriever(indexed_client).search("beneficial ownership threshold twenty five percent")
    assert hits[0].clause_id == "CFR-1010.999(a)"
    assert hits[0].vector_score is not None


def test_final_k_respected(indexed_client):
    assert len(_retriever(indexed_client, final_k=3).search("customer")) == 3


def test_graph_injection_adds_missing_clause(indexed_client):
    hits = _retriever(indexed_client).search(
        "completely unrelated query text zzz", extra_clause_ids=["FATF-R10-IN-¶9"]
    )
    assert any(h.clause_id == "FATF-R10-IN-¶9" for h in hits)


def test_injection_does_not_duplicate_existing_candidate(indexed_client):
    hits = _retriever(indexed_client).search(
        "simplified measures lower risk situations", extra_clause_ids=["FATF-R10-IN-¶9"]
    )
    assert sum(1 for h in hits if h.clause_id == "FATF-R10-IN-¶9") == 1


def test_fake_reranker_reorders(indexed_client):
    class ReverseReranker:
        def score(self, query, texts):
            return list(range(len(texts)))

    hits_plain = _retriever(indexed_client).search("customer identification program")
    hits_rr = _retriever(indexed_client, reranker=ReverseReranker()).search(
        "customer identification program"
    )
    assert [h.clause_id for h in hits_rr] != [h.clause_id for h in hits_plain]
    assert all(h.rerank_score is not None for h in hits_rr)


def test_point_ids_deterministic():
    assert clause_point_id("CFR-1010.230(b)(1)") == clause_point_id("CFR-1010.230(b)(1)")
    assert clause_point_id("A") != clause_point_id("B")


def test_final_k_must_not_exceed_top_k(indexed_client):
    with pytest.raises(ValueError):
        _retriever(indexed_client, final_k=99)
