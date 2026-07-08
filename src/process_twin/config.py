"""Central configuration. Every tunable the brief calls out lives here, never inline.

Design rules (ground rules 2 and 6):
  * Model tiering is config, not code — bulk extraction and synthetic-data generation run
    on the cheap tier; runtime agent decisions and reconciliation run on the strong tier.
    Models are pinned strings so eval numbers are reproducible run-to-run.
  * Guardrail thresholds are fields with documented defaults so an interview answer is
    always one file away ("where does 0.7 come from?" -> here, with the rationale).
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- LLM tiers (ground rule 6: cost discipline) ---
    anthropic_api_key: str | None = None
    model_fast: str = "claude-haiku-4-5-20251001"  # bulk extraction, synthetic data
    model_reasoning: str = "claude-sonnet-5"  # runtime atoms, reconciliation adjudication

    # --- services (defaults match docker-compose.yml) ---
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

    # --- retrieval (brief §7.4; models chosen for CPU laptops, no torch — see architecture.md) ---
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    reranker_model: str = "BAAI/bge-reranker-base"
    retrieval_top_k: int = 8  # vector candidates before rerank
    retrieval_final_k: int = 5  # returned after rerank; probe metric is hit@5

    # --- guardrail thresholds (brief §7.3; each justified in docs/eval-methodology.md) ---
    # 0.7 default: below it, empirically-calibrated LLM confidence is closer to a coin flip
    # than a decision — route to a human instead of proceeding. Revisited with real
    # calibration data in phase 6.
    confidence_threshold: float = 0.7
    # Reranker relevance floor for the citation validator: a cited clause must actually
    # support the decision text, not merely exist. Tuned in phase 4 against probe data.
    citation_relevance_threshold: float = 0.35
    # Schema self-correction loop (brief §6.1): 3 attempts, then dead-letter. More retries
    # mostly re-buys the same failure at 3x the cost.
    max_schema_retries: int = 3

    # --- paths ---
    data_dir: Path = Path("data")
    audit_log_path: Path = Path("data/audit/audit_log.jsonl")
    dead_letter_dir: Path = Path("data/dead_letter")


@lru_cache
def get_settings() -> Settings:
    return Settings()
