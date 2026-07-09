"""Clause parser tests. The property under test is STABILITY: identical source bytes
must produce byte-identical clause records — the citation guardrail depends on it."""

from pathlib import Path

from process_twin.ingestion.policy_pdf import (
    MAX_CLAUSE_CHARS,
    make_record,
    parse_ecfr_xml,
    parse_ffiec_html,
    split_long_clauses,
    write_clauses_jsonl,
)

FIXTURES = Path(__file__).parent / "fixtures"


def _ecfr_records():
    return parse_ecfr_xml((FIXTURES / "ecfr_sample.xml").read_bytes(), section="1010.999")


class TestEcfrParser:
    def test_letter_number_roman_hierarchy(self):
        ids = [r.clause_id for r in _ecfr_records()]
        assert "CFR-1010.999(a)" in ids
        assert "CFR-1010.999(b)(1)" in ids
        assert "CFR-1010.999(b)(2)(i)" in ids
        assert "CFR-1010.999(b)(2)(ii)" in ids

    def test_letter_i_after_h_is_letter_not_roman(self):
        # the classic CFR ambiguity: (h) then (i) — must be top-level letter (i),
        # NOT roman (h)(?)(i). 31 CFR 1010.230 really has paragraphs (a)–(j).
        ids = [r.clause_id for r in _ecfr_records()]
        assert "CFR-1010.999(i)" in ids
        assert not any("(h)" in cid and "(i)" in cid for cid in ids)
        assert "CFR-1010.999(j)" in ids  # sequence continues normally after

    def test_undesignated_paragraph_merges_into_current_clause(self):
        recs = {r.clause_id: r for r in _ecfr_records()}
        assert "undesignated paragraph continues" in recs["CFR-1010.999(i)"].text

    def test_reparse_is_byte_identical(self, tmp_path):
        p1, p2 = tmp_path / "a.jsonl", tmp_path / "b.jsonl"
        write_clauses_jsonl(_ecfr_records(), p1)
        write_clauses_jsonl(_ecfr_records(), p2)
        assert p1.read_bytes() == p2.read_bytes()  # IDs, text, checksums — all stable


class TestFfiecParser:
    def test_noise_removed_content_kept_in_order(self):
        html = (FIXTURES / "ffiec_sample.html").read_text(encoding="utf-8")
        recs = parse_ffiec_html(html, "CIP", "Widget Identification Program")
        texts = " ".join(r.text for r in recs)
        assert "InfoBase" not in texts  # header noise
        assert "footer paragraph" not in texts  # footer noise
        assert "Short crumb." not in texts  # length filter
        assert recs[0].clause_id == "FFIEC-CIP-¶1"
        assert [r.clause_id for r in recs] == [f"FFIEC-CIP-¶{i}" for i in range(1, len(recs) + 1)]

    def test_duplicate_paragraphs_deduped(self):
        html = (FIXTURES / "ffiec_sample.html").read_text(encoding="utf-8")
        recs = parse_ffiec_html(html, "CIP", "t")
        risk_based = [r for r in recs if "risk-based procedures" in r.text]
        assert len(risk_based) == 1  # fixture repeats the paragraph on purpose


class TestSplitting:
    def test_oversized_clause_splits_with_suffixed_ids(self):
        long_text = ". ".join(
            f"Sentence number {i} about widget verification detail" for i in range(80)
        )
        rec = make_record("FFIEC-CDD-¶3", "doc", "sec", long_text)
        assert len(rec.text) > MAX_CLAUSE_CHARS
        out = split_long_clauses([rec])
        assert [r.clause_id for r in out][:2] == ["FFIEC-CDD-¶3a", "FFIEC-CDD-¶3b"]
        assert all(len(r.text) <= MAX_CLAUSE_CHARS for r in out)
        # nothing lost: every sentence lands in exactly one chunk
        rebuilt = " ".join(r.text for r in out)
        assert "Sentence number 0" in rebuilt and "Sentence number 79" in rebuilt

    def test_normal_clause_untouched(self):
        rec = make_record("CFR-1010.999(a)", "doc", "sec", "Short clause.")
        assert split_long_clauses([rec]) == [rec]

    def test_checksum_tracks_text_only(self):
        a = make_record("X-1", "doc", "sec", "Same   text  here")
        b = make_record("X-2", "other doc", "other sec", "Same text here")
        assert a.checksum == b.checksum  # normalization collapses whitespace
        assert a.checksum != make_record("X-3", "doc", "sec", "Different text").checksum
