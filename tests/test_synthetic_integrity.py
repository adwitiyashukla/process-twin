"""Cross-artifact integrity of the synthetic corpus (brief §4.2-4.3, ground rule 3)."""

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
CASE_DIR = ROOT / "data" / "case_logs"
LEDGER = ROOT / "data" / "interviews" / "SYNTHETIC.md"

sys.path.insert(0, str(ROOT / "scripts"))


def _ledger_support() -> dict[str, int]:
    """Parse the 'Log support' column out of the SYNTHETIC.md ledger table."""
    counts = {}
    for line in LEDGER.read_text(encoding="utf-8").splitlines():
        m = re.match(r"\|\s*(D\d+)\s*\|.*\|\s*(\d+)(?:\s*\([^)]*\))?\s*\|\s*$", line)
        if m:
            counts[m.group(1)] = int(m.group(2))
    return counts


def test_ledger_table_parses_all_ten_deltas():
    counts = _ledger_support()
    assert set(counts) == {f"D{i}" for i in range(1, 11)}, counts


def test_committed_cases_match_regeneration_byte_for_byte(tmp_path):
    import generate_case_logs as gen

    gen.write_outputs(tmp_path)
    for fname in ["cases.jsonl", "ground_truth_tags.json", "delta_support.json"]:
        committed = (CASE_DIR / fname).read_bytes()
        regenerated = (tmp_path / fname).read_bytes()
        assert committed == regenerated, f"{fname} drifted from its generator"


def test_distribution_35_18_7():
    tags = json.loads((CASE_DIR / "ground_truth_tags.json").read_text(encoding="utf-8"))
    cats = [t["category"] for t in tags.values()]
    assert len(tags) == 60
    assert cats.count("policy_consistent") == 35
    assert cats.count("tacit_pattern") == 18
    assert cats.count("error") == 7


def test_delta_support_matches_ledger_exactly():
    support = json.loads((CASE_DIR / "delta_support.json").read_text(encoding="utf-8"))
    ledger = _ledger_support()
    for delta, expected in ledger.items():
        assert support.get(delta) == expected, (
            f"{delta}: ledger says {expected}, case logs give {support.get(delta)}"
        )
    assert support["D10_reject"] >= 1 and support["D10_accept"] >= 1


def test_no_ground_truth_leaks_into_case_records():
    raw = (CASE_DIR / "cases.jsonl").read_text(encoding="utf-8")
    assert not re.search(r'"D\d+"', raw)
    for forbidden in ["delta", "tacit_pattern", "policy_consistent", "ground_truth"]:
        assert forbidden not in raw, f"label vocabulary {forbidden!r} leaked into cases.jsonl"


def test_error_cases_are_never_delta_tagged():
    tags = json.loads((CASE_DIR / "ground_truth_tags.json").read_text(encoding="utf-8"))
    for case_id, t in tags.items():
        if t["category"] == "error":
            assert t["deltas"] == [], f"{case_id}: error cases must not support deltas"
            assert "error_kind" in t


def test_every_case_validates_against_schema():
    from process_twin.schemas.case import CaseLog

    lines = (CASE_DIR / "cases.jsonl").read_text(encoding="utf-8").splitlines()
    cases = [CaseLog.model_validate_json(line) for line in lines if line.strip()]
    assert len(cases) == 60
    ids = [c.case_id for c in cases]
    assert len(set(ids)) == 60
    assert ids == sorted(ids)


def test_d1_cases_sit_in_the_2025_boundary_band():
    """Every D1-tagged case must actually exhibit the pattern: legal entity, high-risk"""
    from process_twin.schemas.case import CaseLog

    tags = json.loads((CASE_DIR / "ground_truth_tags.json").read_text(encoding="utf-8"))
    by_id = {}
    for line in (CASE_DIR / "cases.jsonl").read_text(encoding="utf-8").splitlines():
        c = CaseLog.model_validate_json(line)
        by_id[c.case_id] = c
    d1_cases = [cid for cid, t in tags.items() if "D1" in t["deltas"]]
    assert len(d1_cases) == 11
    for cid in d1_cases:
        c = by_id[cid]
        assert c.applicant_profile.applicant_type == "legal_entity"
        band = [o for o in c.applicant_profile.beneficial_owners
                if o.jurisdiction_risk == "high" and 20.0 <= o.ownership_pct < 25.0]
        assert band, f"{cid}: no high-risk owner in the 20-25% band"


def test_transcript_check_passes():
    proc = subprocess.run(
        [sys.executable, "scripts/generate_interviews.py", "--check"],
        cwd=ROOT, capture_output=True, text=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr


@pytest.mark.parametrize("fname", ["personas.yaml", "SYNTHETIC.md"])
def test_interview_artifacts_exist(fname):
    assert (ROOT / "data" / "interviews" / fname).exists()
