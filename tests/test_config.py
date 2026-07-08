"""Config tests: defaults sane, env overrides work, thresholds within meaningful ranges."""

from process_twin.config import Settings


def test_defaults_load_without_env_file():
    s = Settings(_env_file=None)
    assert s.anthropic_api_key is None
    assert s.qdrant_collection == "policy_clauses"
    assert 0.0 < s.confidence_threshold < 1.0
    assert 0.0 < s.citation_relevance_threshold < 1.0
    assert s.max_schema_retries >= 1


def test_model_tiers_are_distinct():
    s = Settings(_env_file=None)
    # ground rule 6: cheap tier for bulk, strong tier for reasoning — never the same knob
    assert s.model_fast != s.model_reasoning
    assert s.model_fast.startswith("claude-")
    assert s.model_reasoning.startswith("claude-")


def test_env_override(monkeypatch):
    monkeypatch.setenv("CONFIDENCE_THRESHOLD", "0.85")
    monkeypatch.setenv("MODEL_FAST", "claude-test-model")
    s = Settings(_env_file=None)
    assert s.confidence_threshold == 0.85
    assert s.model_fast == "claude-test-model"


def test_retrieval_k_ordering():
    s = Settings(_env_file=None)
    # rerank narrows, never widens: final_k must not exceed the candidate pool
    assert s.retrieval_final_k <= s.retrieval_top_k
