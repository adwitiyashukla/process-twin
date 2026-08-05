"""Guardrail tests (§7.3). Every guardrail has at least one test proving it BLOCKS what
it must block — the brief's ground rule 7."""

from process_twin.runtime.guardrails import (
    CitationValidator,
    GuardrailResult,
    confidence_gate,
    delta_guard,
    run_all,
)
from process_twin.schemas.runtime import AtomOutput, Citation

KNOWN = {"CFR-1010.230(b)(1)", "FFIEC-CIP-¶2", "FFIEC-CDD-¶2"}
TEXTS = {
    "CFR-1010.230(b)(1)": "Identify each beneficial owner who owns 25 percent or more equity.",
    "FFIEC-CIP-¶2": "Documentary verification uses unexpired government issued identification.",
    "FFIEC-CDD-¶2": "Enhanced due diligence applies to higher risk customer relationships.",
}


class KeywordReranker:
    """Stand-in cross-encoder: word overlap. Enough to prove the relevance PLUMBING;
    real relevance quality is measured by `make probe` with the BGE reranker."""

    def score(self, query, texts):
        q = set(query.lower().split())
        return [len(q & set(t.lower().split())) / max(len(q), 1) for t in texts]


def out(citations=(), confidence=0.9, needs_human=False, result=None):
    return AtomOutput(result=result or {"decision": "approve"},
                      citations=[Citation(clause_id=c) for c in citations],
                      confidence=confidence, needs_human=needs_human)


class TestCitationValidator:
    def test_blocks_uncited_decision(self):
        r = CitationValidator(KNOWN).validate(out())
        assert not r.passed and r.needs_human and r.reason == "uncited decision"

    def test_blocks_fabricated_clause_id(self):
        # failure mode 1: the model invents a plausible-looking citation
        r = CitationValidator(KNOWN).validate(out(["CFR-9999.111(z)"]))
        assert not r.passed
        assert any("citation_unknown_clause" in v for v in r.violations)

    def test_blocks_real_but_irrelevant_citation(self):
        # failure mode 2 — the subtle one: the clause EXISTS but doesn't support the decision
        v = CitationValidator(KNOWN, KeywordReranker(), TEXTS, threshold=0.3)
        r = v.validate(out(["FFIEC-CDD-¶2"]),
                       decision_text="beneficial owner ownership percentage equity threshold")
        assert not r.passed
        assert any("citation_irrelevant" in x for x in r.violations)

    def test_passes_relevant_existing_citation(self):
        v = CitationValidator(KNOWN, KeywordReranker(), TEXTS, threshold=0.2)
        r = v.validate(out(["CFR-1010.230(b)(1)"]),
                       decision_text="beneficial owner owns 25 percent equity")
        assert r.passed and not r.needs_human

    def test_relevance_score_is_recorded_for_the_trace(self):
        v = CitationValidator(KNOWN, KeywordReranker(), TEXTS, threshold=0.2)
        o = out(["CFR-1010.230(b)(1)"])
        v.validate(o, decision_text="beneficial owner owns 25 percent equity")
        assert o.citations[0].relevance_score is not None


class TestConfidenceGate:
    def test_blocks_below_threshold(self):
        r = confidence_gate(out(["FFIEC-CIP-¶2"], confidence=0.55), threshold=0.7)
        assert not r.passed and r.needs_human and "0.55" in r.reason

    def test_passes_at_threshold(self):
        assert confidence_gate(out(["FFIEC-CIP-¶2"], confidence=0.7), threshold=0.7).passed


class TestDeltaGuard:
    DELTAS = [
        {"id": "DET-001", "severity": "high", "about_element_id": "EL-callback",
         "description": "callback skipped"},
        {"id": "DET-007", "severity": "low", "about_element_id": "EL-screen",
         "description": "sequence"},
    ]

    def test_delta_forces_human(self):
        """The brief names this test explicitly (§7.3(4))."""
        r = delta_guard("EL-callback", self.DELTAS)
        assert not r.passed and r.needs_human and "DET-001" in r.reason

    def test_high_confidence_cannot_override_delta_guard(self):
        # confidence measures self-certainty, NOT which side of an open policy question
        # is right — so a 0.99 atom on a high-severity delta step still goes to a human
        r = run_all(out(["FFIEC-CIP-¶2"], confidence=0.99), "EL-callback", self.DELTAS)
        assert r.needs_human and "DET-001" in r.reason

    def test_low_severity_delta_does_not_block(self):
        assert delta_guard("EL-screen", self.DELTAS).passed

    def test_step_without_delta_passes(self):
        assert delta_guard("EL-verify", self.DELTAS).passed


class TestRunAll:
    def test_delta_reason_wins_over_confidence_reason(self):
        deltas = [{"id": "DET-001", "severity": "high", "about_element_id": "EL-x",
                   "description": "d"}]
        r = run_all(out(["FFIEC-CIP-¶2"], confidence=0.1), "EL-x", deltas)
        assert "DET-001" in r.reason  # most fundamental problem surfaces to the reviewer

    def test_atom_requested_review_is_honored_even_when_all_guardrails_pass(self):
        r = run_all(out(["FFIEC-CIP-¶2"], confidence=0.95, needs_human=True), "EL-x", [])
        assert r.passed and r.needs_human

    def test_clean_output_proceeds(self):
        r = run_all(out(["FFIEC-CIP-¶2"], confidence=0.95), "EL-x", [])
        assert r.passed and not r.needs_human
        assert isinstance(r, GuardrailResult)
