"""Phase-3 ingestion: transcript segmentation stability + the miner↔ledger lockstep.

The lockstep test is the important one: mining cases.jsonl ALONE (no ground-truth
sidecar) must reproduce every support count the SYNTHETIC.md/ledger.yaml ledger claims.
If it can't, either the data lacks evidence or the ledger overclaims — both are bugs.
"""

from pathlib import Path

import yaml

from process_twin.ingestion.case_logs import load_cases, mine_patterns
from process_twin.ingestion.transcripts import load_all_transcripts, segment_transcript

ROOT = Path(__file__).parent.parent
LEDGER = yaml.safe_load((ROOT / "data" / "interviews" / "ledger.yaml").read_text("utf-8"))

# ledger delta id -> miner pattern id(s) that evidence it
DELTA_TO_PATTERN = {
    "D1": ["PAT-BO-SCRUTINY-BAND"],
    "D2": ["PAT-EXPIRED-PASSPORT-RECEIPT"],
    "D3": ["PAT-ADDRESS-MISMATCH-REFERRAL"],
    "D4": ["PAT-SEQ-SCREEN-FIRST"],
    "D5": ["PAT-UTILITY-BILL-60D"],
    "D6": ["PAT-CALLBACK-SKIPPED-SMALL"],
    "D7": ["PAT-VERBAL-PEP-WALKOVER"],
    "D8": ["PAT-MATCH-TOLERANCE-WIDENED"],
    "D9": ["PAT-FOREIGN-TAX-ID-ADHOC"],
    "D10": ["PAT-PO-BOX-ACCEPTED", "PAT-PO-BOX-REJECTED"],
}


class TestSegmenter:
    def test_all_six_personas_segment(self):
        segments = load_all_transcripts(ROOT / "data" / "interviews" / "transcripts")
        personas = {s.persona_id for s in segments}
        assert personas == {f"P{i}" for i in range(1, 7)}
        ids = [s.id for s in segments]
        assert len(ids) == len(set(ids))  # stable AND unique

    def test_segment_ids_and_content(self):
        path = ROOT / "data" / "interviews" / "transcripts" / "P1_priya_raghavan.md"
        segs = segment_transcript(path)
        assert segs[0].id == "P1-S1"
        assert segs[0].persona_name == "Priya Raghavan"
        assert "standard onboarding" in segs[0].question.lower()
        assert len(segs) >= 5  # interview guide has 6 questions
        assert all(len(s.text) > 100 for s in segs)  # answers, not crumbs
        assert all(s.quote_span for s in segs)

    def test_segmentation_is_deterministic(self):
        path = ROOT / "data" / "interviews" / "transcripts" / "P4_jordan_lee.md"
        assert [s.model_dump() for s in segment_transcript(path)] == [
            s.model_dump() for s in segment_transcript(path)
        ]


class TestMiner:
    def test_miner_supports_match_ledger(self):
        """THE lockstep: raw records alone must reproduce every ledger support count."""
        patterns = {p.id: p for p in mine_patterns(load_cases(ROOT / "data/case_logs/cases.jsonl"))}
        for row in LEDGER["deltas"]:
            mined = sum(patterns[pid].support_count for pid in DELTA_TO_PATTERN[row["id"]]
                        if pid in patterns)
            assert mined == row["support"], (
                f"{row['id']}: ledger claims {row['support']}, miner found {mined}"
            )

    def test_error_cases_do_not_leak_into_pattern_support(self):
        patterns = {p.id: p for p in mine_patterns(load_cases(ROOT / "data/case_logs/cases.jsonl"))}
        # E6 (HC-059) has the mismatch trigger but no referral -> must NOT support D3's pattern
        assert "HC-059" not in patterns["PAT-ADDRESS-MISMATCH-REFERRAL"].case_ids
        # E5 (HC-058) skipped callback on a $50k account -> outside the tacit under-$10k band
        assert "HC-058" not in patterns["PAT-CALLBACK-SKIPPED-SMALL"].case_ids

    def test_pattern_case_ids_are_auditable(self):
        cases = {c.case_id: c for c in load_cases(ROOT / "data/case_logs/cases.jsonl")}
        for p in mine_patterns(list(cases.values())):
            assert p.support_count == len(p.case_ids)
            assert all(cid in cases for cid in p.case_ids)
