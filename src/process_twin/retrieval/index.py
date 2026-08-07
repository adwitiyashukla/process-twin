"""Qdrant collection build from processed clauses."""

from __future__ import annotations

import sys
import uuid
from pathlib import Path

from process_twin.ingestion.policy_pdf import ClauseRecord, read_clauses_jsonl
from process_twin.retrieval.embedder import Embedder

BATCH = 64


def clause_point_id(clause_id: str) -> str:
    """Deterministic point id: re-indexing upserts in place instead of duplicating."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"process-twin/clause/{clause_id}"))


def ensure_collection(client, name: str, dim: int) -> None:
    from qdrant_client import models

    existing = {c.name for c in client.get_collections().collections}
    if name in existing:
        info = client.get_collection(name)
        current_dim = info.config.params.vectors.size
        if current_dim != dim:
            raise RuntimeError(
                f"collection {name!r} has dim {current_dim}, embedder produces {dim} - "
                "either drop the collection or fix EMBEDDING_MODEL (refusing to mix spaces)"
            )
        return
    client.create_collection(
        collection_name=name,
        vectors_config=models.VectorParams(size=dim, distance=models.Distance.COSINE),
    )


def index_clauses(client, collection: str, clauses: list[ClauseRecord], embedder: Embedder) -> int:
    from qdrant_client import models

    ensure_collection(client, collection, embedder.dim)
    total = 0
    for start in range(0, len(clauses), BATCH):
        batch = clauses[start : start + BATCH]
        vectors = embedder.embed([c.text for c in batch])
        client.upsert(
            collection_name=collection,
            points=[
                models.PointStruct(
                    id=clause_point_id(c.clause_id),
                    vector=v,
                    payload={
                        "clause_id": c.clause_id,
                        "source_doc": c.source_doc,
                        "section_path": c.section_path,
                        "text": c.text,
                    },
                )
                for c, v in zip(batch, vectors, strict=True)
            ],
        )
        total += len(batch)
    return total


def main() -> int:
    from qdrant_client import QdrantClient

    from process_twin.config import get_settings
    from process_twin.retrieval.embedder import get_embedder

    s = get_settings()
    processed = Path(s.data_dir) / "policies" / "processed"
    files = sorted(processed.glob("*.jsonl"))
    if not files:
        print("No processed clauses. Run `make fetch` then `make parse` first.")
        return 1

    clauses: list[ClauseRecord] = []
    for f in files:
        clauses.extend(read_clauses_jsonl(f))
    print(f"Loaded {len(clauses)} clauses from {len(files)} files.")

    embedder = get_embedder()
    client = QdrantClient(url=s.qdrant_url)
    n = index_clauses(client, s.qdrant_collection, clauses, embedder)
    print(f"Indexed {n} clauses into {s.qdrant_collection!r} @ {s.qdrant_url} "
          f"(model: {getattr(embedder, 'model_name', '?')}, dim={embedder.dim}).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
