"""Reconciliation + delta-detection mechanics.

The detection test feeds fixture canonicals/conflicts shaped like real extraction
output PLUS the real mined patterns from the committed case corpus, and expects every
ledger row recovered. That proves the RULES; the headline P/R number in the README
comes only from the full run with real LLM extraction (Adi's machine, seed_graph).
"""

from pathlib import Path

from process_twin.extraction.delta_detect import detect_deltas, score_against_ledger
from process_twin.extraction.reconcile import reconcile
from process_twin.ingestion.case_logs import load_cases, mine_patterns
from process_twin.retrieval.embedder import HashingEmbedder
from process_twin.schemas.process import (
    AttributeConflict,
    CanonicalElement,
    ProcessElement,
    SourceSpan,
)

ROOT = Path(__file__).parent.parent


def span(st, ref):
    return SourceSpan(source_type=st, ref=ref)


def pe(name, desc, st, ref, etype="step", attrs=None, seq=None):
    return ProcessElement(
        element_type=etype, name=name, description=desc, actor="human",
        attributes=attrs or {}, sequence_hint=seq,
        source_spans=[span(st, ref)], extractor_confidence=0.85,
    )


class TestReconcile:
    def test_same_element_across_sources_merges_with_written_name_winning(self):
        els = [
            pe("check identity documents", "Check identity documents provided by the customer.",
               "interview", "P1-S1"),
            pe("verify identity documents", "Verify identity documents provided by the customer.",
               "policy", "FFIEC-CIP-¶2", seq=2),
        ]
        canon, _ = reconcile(els, HashingEmbedder())
        assert len(canon) == 1
        assert canon[0].name == "verify identity documents"  # written wins the name
        assert canon[0].sequence_hint == 2  # written order is canonical order
        assert {s.source_type for s in canon[0].provenance} == {"interview", "policy"}
        assert canon[0].confidence > 0.85  # agreement boosts, never averages

    def test_distinct_elements_stay_separate(self):
        els = [
            pe("screen sanctions lists", "Run the applicant against sanctions lists.",
               "policy", "FFIEC-CDD-¶4"),
            pe("compute risk rating", "Assign the customer risk rating from collected factors.",
               "policy", "FFIEC-CDD-¶9"),
        ]
        assert len(reconcile(els, HashingEmbedder())[0]) == 2

    def test_same_key_disagreement_becomes_conflict_and_written_stays_canonical(self):
        els = [
            pe("accept utility bill", "Utility bill accepted as proof of address, max age.",
               "policy", "FFIEC-CIP-¶5", attrs={"utility_bill_max_age_days": "90"}),
            pe("accept utility bill", "Utility bill accepted as proof of address, max age.",
               "interview", "P1-S3", attrs={"utility_bill_max_age_days": "60"}),
        ]
        canon, conflicts = reconcile(els, HashingEmbedder())
        assert canon[0].attributes["utility_bill_max_age_days"] == "90"  # never averaged
        assert len(conflicts) == 1
        cf = conflicts[0]
        assert (cf.written_value, cf.practiced_value) == ("90", "60")

    def test_practice_only_attribute_is_flagged_not_silently_adopted(self):
        els = [
            pe("check beneficial ownership", "Collect and verify the ownership certification.",
               "policy", "CFR-1010.230(b)(1)", attrs={"bo_threshold_pct": "25"}),
            pe("check beneficial ownership", "Collect and verify the ownership certification.",
               "interview", "P3-S2", attrs={"bo_scrutiny_pct": "20"}),
        ]
        canon, conflicts = reconcile(els, HashingEmbedder())
        flagged = [c for c in conflicts if c.attribute == "bo_scrutiny_pct"]
        assert flagged and flagged[0].written_value is None
        assert canon[0].attributes["bo_threshold_pct"] == "25"


def _fixture_inputs():
    """Canonicals + conflicts shaped like a real reconciliation over all three sources."""
    patterns = mine_patterns(load_cases(ROOT / "data/case_logs/cases.jsonl"))

    def ce(id_, etype, name, desc, prov, attrs=None, seq=None):
        return CanonicalElement(
            id=id_, element_type=etype, name=name, description=desc, actor="human",
            attributes=attrs or {}, sequence_hint=seq, confidence=0.9, provenance=prov,
        )

    canonicals = [
        ce("EL-check_beneficial_ownership", "step", "check beneficial ownership",
           "Identify and verify beneficial owners of legal entity customers.",
           [span("policy", "CFR-1010.230(b)(1)"), span("interview", "P3-S2")],
           {"bo_threshold_pct": "25"}, seq=5),
        ce("EL-verify_identity_documents", "step", "verify identity documents",
           "Documentary verification of customer identity.",
           [span("policy", "FFIEC-CIP-¶2")], seq=2),
        ce("EL-screen_sanctions_pep", "step", "screen sanctions and pep lists",
           "Screen the applicant against sanctions and PEP lists.",
           [span("policy", "FFIEC-CDD-¶4"), span("case_log", "PAT-SEQ-SCREEN-FIRST")], seq=3),
        ce("EL-address_mismatch_referral", "exception", "two address mismatches referral",
           "Two address mismatches across documents trigger an automatic EDD referral.",
           [span("interview", "P4-S3"), span("case_log", "PAT-ADDRESS-MISMATCH-REFERRAL")]),
        ce("EL-expired_passport_receipt", "exception",
           "accept expired passport with renewal receipt",
           "Expired passport accepted with official renewal receipt and 30-day follow-up.",
           [span("interview", "P4-S2"), span("case_log", "PAT-EXPIRED-PASSPORT-RECEIPT")]),
        ce("EL-verbal_pep_walkover", "escalation", "verbal pep close-associate walkover",
           "PEP close-associate cases briefed verbally to compliance before any ticket.",
           [span("interview", "P3-S3"), span("interview", "P5-S3")]),
        ce("EL-foreign_tax_id_review", "exception", "foreign tax id ad hoc review",
           "Applicants with a foreign tax ID only go to the EDD specialist ad hoc.",
           [span("interview", "P5-S5"), span("case_log", "PAT-FOREIGN-TAX-ID-ADHOC")]),
        ce("EL-red_herring_notes", "step", "retype lost case notes",
           "The case system loses free-text notes on session timeout.",
           [span("interview", "P1-S7")]),  # must NOT become a delta
    ]
    conflicts = [
        AttributeConflict(
            element_id="EL-check_beneficial_ownership",
            element_name="check beneficial ownership", attribute="bo_scrutiny_pct",
            written_value=None, practiced_value="20",
            practiced_spans=[span("interview", "P1-S2"), span("interview", "P3-S2")],
        ),
        AttributeConflict(
            element_id="EL-proof_of_address", element_name="accept utility bill",
            attribute="utility_bill_max_age_days", written_value="90", practiced_value="60",
            written_spans=[span("policy", "FFIEC-CIP-¶5")],
            practiced_spans=[span("interview", "P1-S3")],
        ),
        AttributeConflict(
            element_id="EL-callback_verification", element_name="callback verification",
            attribute="callback_min_activity_usd", written_value=None, practiced_value="10000",
            written_spans=[span("policy", "FFIEC-CIP-¶7")],
            practiced_spans=[span("interview", "P4-S4")],
        ),
        AttributeConflict(
            element_id="EL-screen_sanctions_pep", element_name="screen sanctions and pep lists",
            attribute="screening_match_tolerance", written_value=None, practiced_value="widened",
            practiced_spans=[span("interview", "P1-S4"), span("interview", "P5-S4")],
        ),
    ]
    return canonicals, conflicts, patterns


class TestDeltaDetection:
    def test_all_ten_ledger_rows_recovered_from_fixture_inputs(self):
        canonicals, conflicts, patterns = _fixture_inputs()
        deltas = detect_deltas(canonicals, conflicts, patterns)
        score = score_against_ledger(deltas, ROOT / "data/interviews/ledger.yaml")
        assert score["missed_rows"] == [], score
        assert score["recall"] == 1.0
        assert score["precision"] == 1.0, score  # red herring must not produce a delta

    def test_severities_follow_the_rubric(self):
        canonicals, conflicts, patterns = _fixture_inputs()
        detected = detect_deltas(canonicals, conflicts, patterns)
        by_kind_desc = {(d.kind, d.severity) for d in detected}
        assert ("threshold", "high") in by_kind_desc  # regulatory threshold -> high
        assert ("skipped_step", "high") in by_kind_desc  # skipped control -> high
        assert ("sequence", "low") in by_kind_desc  # ordering/efficiency -> low

    def test_support_counts_come_from_mined_patterns(self):
        canonicals, conflicts, patterns = _fixture_inputs()
        deltas = detect_deltas(canonicals, conflicts, patterns)
        d1 = next(d for d in deltas if d.kind == "threshold" and "25%" in d.description)
        assert d1.support_count == 11  # "seen in 11 of 60 historical cases"
        d10 = next(d for d in deltas if d.kind == "practitioner_conflict")
        assert d10.support_count == 4

    def test_every_delta_has_evidence_and_recommendation(self):
        canonicals, conflicts, patterns = _fixture_inputs()
        for d in detect_deltas(canonicals, conflicts, patterns):
            assert d.practiced_view, d.id  # a delta with no practiced evidence is a bug
            assert d.recommendation
