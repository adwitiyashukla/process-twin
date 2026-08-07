"""Langfuse bootstrap: one trace per case, one span per atom, one generation per call."""

from __future__ import annotations

import contextlib
from typing import Any

from process_twin.config import get_settings

MODEL_COSTS_USD_PER_MTOK: dict[str, tuple[float, float]] = {
    "claude-haiku-4-5": (1.00, 5.00),
    "claude-sonnet-5": (3.00, 15.00),
}

_client: Any | None = None
_client_initialized = False


def estimate_cost_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    """Prefix-match the price table; unknown models cost 0.0 (never invent numbers -"""
    for prefix, (in_rate, out_rate) in MODEL_COSTS_USD_PER_MTOK.items():
        if model.startswith(prefix):
            return (input_tokens * in_rate + output_tokens * out_rate) / 1_000_000
    return 0.0


def get_client() -> Any | None:
    """Singleton Langfuse client, or None when keys are absent (no-op mode)."""
    global _client, _client_initialized
    if _client_initialized:
        return _client
    _client_initialized = True
    s = get_settings()
    if not (s.langfuse_public_key and s.langfuse_secret_key):
        _client = None
        return None
    from langfuse import Langfuse

    _client = Langfuse(
        public_key=s.langfuse_public_key,
        secret_key=s.langfuse_secret_key,
        host=s.langfuse_host,
    )
    return _client


def start_case_trace(case_id: str, **tags: Any) -> Any | None:
    """One trace per case, tagged with case_id, golden_case_id and run for filtering."""
    client = get_client()
    if client is None:
        return None
    return client.trace(name=f"case:{case_id}", metadata={"case_id": case_id, **tags})


@contextlib.contextmanager
def atom_span(trace: Any | None, step_id: str, atom_input: dict | None = None):
    """One span per atom execution. Yields the span (or None in no-op mode)."""
    if trace is None:
        yield None
        return
    span = trace.span(name=f"atom:{step_id}", input=atom_input)
    try:
        yield span
    finally:
        span.end()


def log_generation(
    parent: Any | None,
    *,
    name: str,
    model: str,
    input_payload: Any,
    output_payload: Any,
    input_tokens: int,
    output_tokens: int,
) -> float:
    """Attach a generation (LLM call) to a span/trace. Returns estimated cost in USD"""
    cost = estimate_cost_usd(model, input_tokens, output_tokens)
    if parent is not None:
        parent.generation(
            name=name,
            model=model,
            input=input_payload,
            output=output_payload,
            usage={"input": input_tokens, "output": output_tokens, "unit": "TOKENS"},
            metadata={"estimated_cost_usd": round(cost, 6)},
        )
    return cost


def flush() -> None:
    """Langfuse batches over HTTP; short-lived scripts must flush before exit."""
    if _client is not None:
        _client.flush()


def reset_for_tests() -> None:
    """Test hook: clear the cached client so env changes take effect."""
    global _client, _client_initialized
    _client = None
    _client_initialized = False
