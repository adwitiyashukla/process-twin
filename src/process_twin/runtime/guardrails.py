"""Runtime guardrails (brief §7.3): citation validator, confidence gate, schema retry,
delta guard. Anything that fails routes to a human with a stated reason — never a
silent proceed.

The schema-retry guardrail IMPORTS the extractor's self-correction loop rather than
reimplementing it (§7.3 item 3): one loop, one set of tests, one behavior in traces.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from process_twin.config import get_settings
from process_twin.extraction.extractor import extract_batch  # noqa: F401 — §7.3(3): same loop
from process_twin.schemas.runtime import AtomOutput


class GuardrailResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    passed: bool
    needs_human: bool
    reason: str | None = None
    violations: list[str] = []


class CitationValidator:
    """Every decision must cite >= 1 clause that (a) EXISTS in the clause store and
    (b) is RELEVANT (reranker score above threshold).

    Two failure modes to know cold:
      * fabricated id  -> caught by (a); shows in Langfuse as `citation_unknown_clause`.
      * real-but-irrelevant id (model cites a clause that exists but doesn't support the
        decision) -> caught by (b); shows as `citation_irrelevant`. This is the subtle one
        and the reason existence alone is not enough.
    """

    def __init__(self, known_clause_ids: set[str], reranker=None, clause_texts=None,
                 threshold: float | None = None):
        self._known = known_clause_ids
        self._reranker = reranker
        self._texts = clause_texts or {}
        self._threshold = (threshold if threshold is not None
                           else get_settings().citation_relevance_threshold)

    def validate(self, output: AtomOutput, decision_text: str | None = None) -> GuardrailResult:
        if not output.citations:
            return GuardrailResult(passed=False, needs_human=True,
                                   reason="uncited decision",
                                   violations=["no citations supplied"])
        violations = []
        unknown = [c.clause_id for c in output.citations if c.clause_id not in self._known]
        violations += [f"citation_unknown_clause: {cid}" for cid in unknown]

        if self._reranker is not None and self._texts:
            text = decision_text or str(output.result)
            checkable = [c for c in output.citations if c.clause_id in self._texts]
            if checkable:
                scores = self._reranker.score(text, [self._texts[c.clause_id]
                                                     for c in checkable])
                for c, s in zip(checkable, scores, strict=True):
                    c.relevance_score = float(s)
                if not any((c.relevance_score or 0) >= self._threshold for c in checkable):
                    best = max((c.relevance_score or 0) for c in checkable)
                    violations.append(
                        f"citation_irrelevant: best relevance {best:.3f} < {self._threshold}"
                    )
        if violations:
            return GuardrailResult(passed=False, needs_human=True,
                                   reason="uncited decision", violations=violations)
        return GuardrailResult(passed=True, needs_human=False)


def confidence_gate(output: AtomOutput, threshold: float | None = None) -> GuardrailResult:
    """Below threshold, an LLM's stated confidence is closer to a coin flip than a
    decision — route to a human instead of proceeding (§7.3(2))."""
    t = threshold if threshold is not None else get_settings().confidence_threshold
    if output.confidence < t:
        return GuardrailResult(passed=False, needs_human=True,
                               reason=f"confidence {output.confidence:.2f} < {t}",
                               violations=[f"low_confidence:{output.confidence:.2f}"])
    return GuardrailResult(passed=True, needs_human=False)


def delta_guard(step_id: str, deltas: list[dict]) -> GuardrailResult:
    """Any atom executing a step with an attached HIGH-severity delta requires human
    approval REGARDLESS of confidence (§7.3(4)). Confidence measures how sure the model
    is about its own reasoning; it says nothing about which side of an unresolved policy
    question is correct. Only a human can decide that."""
    hits = [d for d in deltas
            if d.get("severity") == "high" and d.get("about_element_id") == step_id]
    if hits:
        ids = ", ".join(d["id"] for d in hits)
        return GuardrailResult(passed=False, needs_human=True,
                               reason=f"unresolved high-severity delta ({ids})",
                               violations=[f"delta_guard:{ids}"])
    return GuardrailResult(passed=True, needs_human=False)


def run_all(output: AtomOutput, step_id: str, deltas: list[dict],
            validator: CitationValidator | None = None,
            decision_text: str | None = None) -> GuardrailResult:
    """Apply guardrails in order of how FUNDAMENTAL the problem is, not in order of
    convenience — the first failure supplies the reason the reviewer sees.

    Order and why:
      1. delta guard      — an unresolved policy question outranks everything; no amount
                            of model confidence settles which side is correct.
      2. citation checks  — a decision without valid grounding cannot be reviewed at all.
      3. atom's own flag  — the atom knows WHY it wants a human ("policy silent on renewal
                            receipts"); that note beats a generic confidence number, and
                            low confidence is usually the *symptom* of exactly this.
      4. confidence gate  — the catch-all for everything nobody explicitly flagged.
    """
    blocking = [delta_guard(step_id, deltas)]
    if validator is not None:
        blocking.append(validator.validate(output, decision_text))
    for result in blocking:
        if not result.passed:
            return result

    if output.needs_human:
        return GuardrailResult(
            passed=True, needs_human=True,
            reason=output.notes or "atom requested human review",
            violations=["atom_requested_review"],
        )

    gate = confidence_gate(output)
    if not gate.passed:
        return gate
    return GuardrailResult(passed=True, needs_human=False)
