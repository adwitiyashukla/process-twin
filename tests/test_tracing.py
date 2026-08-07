"""Tracing tests: the no-op guarantee (keyless never fails) and cost math (ground rule 6)."""

import pytest

from process_twin.observability import tracing


@pytest.fixture(autouse=True)
def _fresh_client_cache(monkeypatch):
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
    from process_twin.config import get_settings

    get_settings.cache_clear()
    tracing.reset_for_tests()
    yield
    get_settings.cache_clear()
    tracing.reset_for_tests()


def test_no_keys_means_noop_client():
    assert tracing.get_client() is None


def test_trace_and_span_are_none_safe():
    trace = tracing.start_case_trace("CASE-X", model_tier="fast")
    assert trace is None
    with tracing.atom_span(trace, "step-1", {"a": 1}) as span:
        assert span is None


def test_log_generation_returns_cost_even_in_noop_mode():
    cost = tracing.log_generation(
        None,
        name="g",
        model="claude-haiku-4-5-20251001",
        input_payload="x",
        output_payload="y",
        input_tokens=1000,
        output_tokens=1000,
    )
    assert cost == pytest.approx(0.006)


def test_unknown_model_costs_zero_not_invented():
    assert tracing.estimate_cost_usd("some-future-model", 10_000, 10_000) == 0.0


def test_flush_is_safe_without_client():
    tracing.flush()
