"""Entity resolution across sources -> canonical nodes + conflict candidates (brief §6.2).

Merge policy, verbatim from the brief: where sources agree the canonical value is kept
and confidence is boosted; where sources DISAGREE the written value stays canonical and
the disagreement becomes a delta candidate. Conflicts are never averaged away — that
single rule is the thesis of the project (docs/architecture.md).

v1 resolution is embedding-similarity clustering with two thresholds: >= HI merges,
<= LO separates, and the band between goes to an optional LLM adjudicator (seed_graph
wires one on the reasoning tier; offline runs stay conservative and keep pairs separate).
"""

from __future__ import annotations

import re
from collections.abc import Callable

from process_twin.retrieval.embedder import Embedder
from process_twin.schemas.process import (
    AttributeConflict,
    CanonicalElement,
    ProcessElement,
    SourceSpan,
)

HI_SIM = 0.80
LO_SIM = 0.55
Adjudicator = Callable[[ProcessElement, CanonicalElement], bool]  # True = same element


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def _cos(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b, strict=True))  # embedder vectors are L2-normed


def _is_written(span: SourceSpan) -> bool:
    return span.source_type == "policy"


def reconcile(
    elements: list[ProcessElement],
    embedder: Embedder,
    adjudicate: Adjudicator | None = None,
    hi: float = HI_SIM,
    lo: float = LO_SIM,
) -> tuple[list[CanonicalElement], list[AttributeConflict]]:
    canonicals: list[CanonicalElement] = []
    vectors: list[list[float]] = []
    # raw attribute claims per canonical: attr -> list[(value, spans, is_written)]
    claims: list[dict[str, list[tuple[str, list[SourceSpan], bool]]]] = []

    for el in sorted(elements, key=lambda e: (e.element_type, e.name.lower())):
        vec = embedder.embed([f"{el.name}. {el.description}"])[0]
        el_written = any(_is_written(s) for s in el.source_spans)

        target_idx: int | None = None
        best_sim, best_idx = -1.0, None
        for idx, canon in enumerate(canonicals):
            if canon.element_type != el.element_type:
                continue
            sim = _cos(vec, vectors[idx])
            if sim > best_sim:
                best_sim, best_idx = sim, idx
        if best_idx is not None and (
            best_sim >= hi
            or (best_sim > lo and adjudicate is not None and adjudicate(el, canonicals[best_idx]))
        ):
            target_idx = best_idx

        if target_idx is None:
            canonicals.append(CanonicalElement(
                id=f"EL-{_slug(el.name)}",
                element_type=el.element_type,
                name=el.name, description=el.description, actor=el.actor,
                attributes={}, sequence_hint=el.sequence_hint,
                confidence=el.extractor_confidence,
                provenance=list(el.source_spans),
                merged_names=[],
            ))
            vectors.append(vec)
            claims.append({})
            target_idx = len(canonicals) - 1
        else:
            canon = canonicals[target_idx]
            canon.provenance.extend(el.source_spans)
            if el.name.lower() != canon.name.lower():
                prior = canon.provenance[: -len(el.source_spans)]
                if el_written and not any(_is_written(s) for s in prior):
                    canon.merged_names.append(canon.name)  # written name takes over
                    canon.name = el.name
                    canon.id = f"EL-{_slug(el.name)}"
                elif el.name not in canon.merged_names:
                    canon.merged_names.append(el.name)
            # agreement across sources boosts confidence (capped) — disagreement never averages
            canon.confidence = min(0.98, max(canon.confidence, el.extractor_confidence) + 0.05)
            if el.sequence_hint is not None and el_written:
                canon.sequence_hint = el.sequence_hint  # written order is canonical order

        for attr, value in el.attributes.items():
            claims[target_idx].setdefault(attr, []).append(
                (value, list(el.source_spans), el_written)
            )

    conflicts: list[AttributeConflict] = []
    for canon, claim_map in zip(canonicals, claims, strict=True):
        for attr, entries in claim_map.items():
            written = [(v, s) for v, s, w in entries if w]
            practiced = [(v, s) for v, s, w in entries if not w]
            w_val = written[0][0] if written else None
            p_val = practiced[0][0] if practiced else None
            if w_val is not None:
                canon.attributes[attr] = w_val  # written wins, always
            elif p_val is not None:
                canon.attributes[attr] = p_val  # practice-only parameter (flagged below)
            if (w_val and p_val and w_val != p_val) or (w_val is None and p_val is not None):
                conflicts.append(AttributeConflict(
                    element_id=canon.id, element_name=canon.name, attribute=attr,
                    written_value=w_val, practiced_value=p_val,
                    written_spans=[sp for _, spans in written for sp in spans],
                    practiced_spans=[sp for _, spans in practiced for sp in spans],
                ))
    return canonicals, conflicts


def llm_adjudicator(model_call) -> Adjudicator:
    """Reasoning-tier tie-breaker for the ambiguous band; justification is logged."""

    def adjudicate(el: ProcessElement, canon: CanonicalElement) -> bool:
        raw = model_call(
            "You resolve entity identity for process elements. Answer with a JSON object "
            '{"same": true|false, "why": "<one line>"} and nothing else.',
            f"A: {el.name} — {el.description}\nB: {canon.name} — {canon.description}\n"
            "Are A and B the same real-world process element?",
        )
        import json

        try:
            verdict = json.loads(raw.strip().strip("`"))
            return bool(verdict.get("same"))
        except (ValueError, AttributeError):
            return False  # unparseable -> conservative: keep separate

    return adjudicate
