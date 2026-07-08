"""Atom contract + registry (brief §7.2), plus the phase-0 hello-world atom.

An atom is the smallest governed unit of work: AtomInput -> AtomOutput, always.
The seven v1 KYC atoms (verify_identity_documents, screen_sanctions_pep,
assess_jurisdiction_risk, check_beneficial_ownership, compute_risk_rating,
determine_edd_requirement, final_onboarding_decision) arrive in Phase 4, each grounded
by retrieval (§7.4). Phase 0 ships one deliberately trivial atom to prove the full
pipe: model call -> schema validation -> trace with cost in Langfuse.
"""

from __future__ import annotations

import json
from collections.abc import Callable

from process_twin.config import get_settings
from process_twin.observability import tracing
from process_twin.schemas.runtime import AtomInput, AtomOutput

AtomFn = Callable[[AtomInput], AtomOutput]
_REGISTRY: dict[str, AtomFn] = {}


def register_atom(name: str) -> Callable[[AtomFn], AtomFn]:
    def deco(fn: AtomFn) -> AtomFn:
        if name in _REGISTRY:
            raise ValueError(f"atom {name!r} already registered")
        _REGISTRY[name] = fn
        return fn

    return deco


def get_atom(name: str) -> AtomFn:
    try:
        return _REGISTRY[name]
    except KeyError:
        raise KeyError(f"unknown atom {name!r}; registered: {sorted(_REGISTRY)}") from None


HELLO_SYSTEM = (
    "You are a component self-test inside a KYC onboarding workflow. "
    "Reply with ONLY a JSON object: "
    '{"greeting": "<one short sentence greeting the operator>", "confidence": <float 0..1>}'
)


def run_hello_atom(dry_run: bool = False, trace=None) -> tuple[AtomOutput, float]:
    """Phase-0 acceptance atom. Returns (validated output, estimated cost in USD).

    dry_run uses a canned model response and touches no network — the exact pattern CI
    and keyless dev rely on, and the same seam later phases reuse for compiler tests.
    """
    settings = get_settings()
    atom_input = AtomInput(case_id="CASE-HELLO", step_id="hello_world", payload={})

    with tracing.atom_span(trace, "hello_world", atom_input.model_dump()) as span:
        if dry_run:
            raw = json.dumps(
                {
                    "greeting": "Hello from process-twin (dry run — no model called).",
                    "confidence": 0.99,
                }
            )
            in_tok, out_tok = 0, 0
        else:
            import anthropic  # lazy: dry-run path must not require the package at import time

            client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
            msg = client.messages.create(
                model=settings.model_fast,  # cheap tier — ground rule 6
                max_tokens=200,
                system=HELLO_SYSTEM,
                messages=[{"role": "user", "content": "Run the self-test."}],
            )
            raw = msg.content[0].text
            in_tok, out_tok = msg.usage.input_tokens, msg.usage.output_tokens

        parsed = json.loads(raw)
        output = AtomOutput(
            result={"greeting": parsed["greeting"]},
            citations=[],  # citations become mandatory for decision atoms in phase 4 (§7.3)
            confidence=float(parsed["confidence"]),
            needs_human=False,
            notes="phase-0 hello atom: proves model call -> schema validation -> traced cost",
        )
        cost = tracing.log_generation(
            span,
            name="hello_world.completion",
            model=settings.model_fast if not dry_run else "dry-run",
            input_payload=HELLO_SYSTEM,
            output_payload=raw,
            input_tokens=in_tok,
            output_tokens=out_tok,
        )
    return output, cost
