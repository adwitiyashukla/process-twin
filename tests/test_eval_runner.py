"""Golden suite integrity, metric definitions, hard gates, and report generation."""

from pathlib import Path

import yaml

from process_twin.evaluation.metrics import (
    THRESHOLDS,
    CaseEvaluation,
    compute_metrics,
    confidence_calibration,
    path_fidelity,
    verdict,
)
from process_twin.evaluation.report import generate
from process_twin.evaluation.runner import run_suite

ROOT = Path(__file__).parent.parent
SUITE = yaml.safe_load((ROOT / "data/golden_cases/suite.yaml").read_text(encoding="utf-8"))


class TestSuiteIntegrity:
    def test_taxonomy_is_the_shape_i_designed(self):
        counts = {}
        for c in SUITE["cases"]:
            counts[c["category"]] = counts.get(c["category"], 0) + 1
        assert counts == {"clean": 12, "documentary_edge": 10, "risk_edd": 8,
                          "adversarial": 6, "policy_conflict": 4}
        assert len(SUITE["cases"]) == 40

    def test_ids_unique_and_fields_present(self):
        ids = [c["id"] for c in SUITE["cases"]]
        assert len(set(ids)) == 40
        for c in SUITE["cases"]:
            assert c["expected_outcome"] in {"approved", "edd_escalated", "rejected",
                                             "pending_information"}
            assert c["expected_path"] and c["must_cite"]

    def test_every_policy_conflict_case_expects_escalation(self):
        """The hard gate only means something if the cases encode it."""
        for c in SUITE["cases"]:
            if c["category"] == "policy_conflict":
                assert c["expected_escalation"] is True
                assert c["expected_outcome"] == "edd_escalated"
                assert "targets_delta" in c

    def test_clean_cases_expect_no_escalation(self):
        """Clean cases are what measure false-positive escalation."""
        for c in SUITE["cases"]:
            if c["category"] == "clean":
                assert c["expected_escalation"] is False
                assert c["expected_outcome"] == "approved"

    def test_targeted_deltas_exist_in_the_ledger(self):
        ledger = yaml.safe_load((ROOT / "data/interviews/ledger.yaml").read_text("utf-8"))
        known = {d["id"] for d in ledger["deltas"]}
        for c in SUITE["cases"]:
            if "targets_delta" in c:
                assert c["targets_delta"] in known, c["id"]


class TestPathFidelity:
    EXPECTED = ["a", "b", "c", "d"]

    def test_completed_case_needs_every_step_in_order(self):
        assert path_fidelity(self.EXPECTED, ["a", "b", "c", "d"])
        assert not path_fidelity(self.EXPECTED, ["a", "c", "b", "d"])
        assert not path_fidelity(self.EXPECTED, ["a", "b", "d"])

    def test_extra_steps_are_not_a_violation(self):
        assert path_fidelity(self.EXPECTED, ["a", "x", "b", "y", "c", "d"])

    def test_escalated_case_only_needs_a_prefix(self):
        assert path_fidelity(self.EXPECTED, ["a", "b"], stopped_early=True)
        assert not path_fidelity(self.EXPECTED, ["b", "a"], stopped_early=True)
        assert not path_fidelity(self.EXPECTED, ["a", "c"], stopped_early=True)


class TestHardGate:
    def _evals(self, conflict_escalated: bool):
        return [
            CaseEvaluation(case_id="GC-037", category="policy_conflict",
                           expected_outcome="edd_escalated",
                           actual_outcome="edd_escalated" if conflict_escalated else "approved",
                           outcome_correct=conflict_escalated,
                           expected_escalation=True, actual_escalation=conflict_escalated),
            *[CaseEvaluation(case_id=f"GC-{i:03d}", category="clean",
                             expected_outcome="approved", actual_outcome="approved",
                             outcome_correct=True) for i in range(1, 13)],
        ]

    def test_missed_policy_conflict_forces_no_go(self):
        metrics = compute_metrics(self._evals(conflict_escalated=False))
        status, failures = verdict(metrics)
        assert status == "NO-GO"
        assert "escalation_recall_policy_conflict" in failures
        gate = next(m for m in metrics if m.name == "escalation_recall_policy_conflict")
        assert gate.hard_gate and gate.threshold == 1.0

    def test_caught_policy_conflict_allows_go(self):
        assert verdict(compute_metrics(self._evals(conflict_escalated=True)))[0] == "GO"

    def test_threshold_asymmetry_is_intentional(self):
        assert THRESHOLDS["escalation_recall_policy_conflict"] == 1.0
        assert THRESHOLDS["outcome_accuracy"] < 1.0


class TestFullSuiteRun:
    def test_suite_runs_and_meets_every_threshold(self):
        evals = run_suite()
        assert len(evals) == 40
        metrics = compute_metrics(evals)
        status, failures = verdict(metrics)
        assert status == "GO", failures

    def test_clean_cases_never_escalate(self):
        """False-positive escalation is what makes a governance system unusable in practice."""
        evals = run_suite()
        assert not [e.case_id for e in evals if e.category == "clean" and e.actual_escalation]

    def test_every_policy_conflict_case_routes_to_a_human(self):
        evals = run_suite()
        conflicts = [e for e in evals if e.category == "policy_conflict"]
        assert conflicts and all(e.actual_escalation for e in conflicts)

    def test_calibration_reported(self):
        calib = confidence_calibration(run_suite())
        assert calib["brier_score"] is not None
        assert sum(b["n"] for b in calib["buckets"].values()) > 0


def test_report_generation(tmp_path):
    evals = run_suite()
    run_dir = generate(evals, out_dir=tmp_path / "run")
    md = (run_dir / "report.md").read_text(encoding="utf-8")
    html = (run_dir / "report.html").read_text(encoding="utf-8")
    assert "Verdict:" in md and "Go/no-go thresholds" in md
    assert "Confidence calibration" in md and "Per-category breakdown" in md
    assert html.startswith("<!DOCTYPE html>") and "<table>" in html
    assert (run_dir / "summary.json").exists()
