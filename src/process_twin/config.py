"""Central configuration. Every tunable lives here, never inline in the code."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    anthropic_api_key: str | None = None
    model_fast: str = "claude-haiku-4-5-20251001"
    model_reasoning: str = "claude-sonnet-5"

    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "processtwin"
    qdrant_url: str = "http://localhost:6333"
    qdrant_collection: str = "policy_clauses"
    temporal_address: str = "localhost:7233"
    temporal_namespace: str = "default"
    temporal_task_queue: str = "process-twin-cases"
    langfuse_host: str = "http://localhost:3000"
    langfuse_public_key: str | None = None
    langfuse_secret_key: str | None = None

    embedding_model: str = "BAAI/bge-small-en-v1.5"
    reranker_model: str = "BAAI/bge-reranker-base"
    retrieval_top_k: int = 8
    retrieval_final_k: int = 5

    confidence_threshold: float = 0.7
    citation_relevance_threshold: float = 0.35
    max_schema_retries: int = 3

    data_dir: Path = Path("data")
    audit_log_path: Path = Path("data/audit/audit_log.jsonl")
    dead_letter_dir: Path = Path("data/dead_letter")


@lru_cache
def get_settings() -> Settings:
    return Settings()
