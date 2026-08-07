"""Audit chain, approval store, and end-to-end executor behaviour."""

import subprocess
import sys
from pathlib import Path

import pytest

from process_twin.runtime.compiler import compile_workflow
from process_twin.runtime.executor import execute_case
from process_twin.runtime.hitl import ApprovalStore
from process_twin.schemas.audit import AuditLog
from process_twin.schemas.runtime import AtomOutput, Citation

ROOT = Path(__file__).parent.parent

PROCESS = {
    "steps": [
        {"id": "EL-collect", "name": "collect customer information", "sequence_hint": 1,
         "step_type": "task", "evidence_required": [], "controls": [],
         "next": [{"target": "EL-verify", "condition": None}]},
        {"id": "EL-verify", "name": "verify identity documents", "sequence_hint": 2,
         "step_type": "task", "evidence_required": ["passport"], "controls": [],
         "next": [{"target": "EL-screen", "condition": None}]},
        {"id": "EL-screen", "name": "screen sanctions and pep lists", "sequence_hint": 3,
         "step_type": "task", "evidence_required": [], "controls": [],
         "next": [{"target": "EL-juris", "condition": None}]},
        {"id": "EL-juris", "name": "assess jurisdiction risk", "sequence_hint": 4,
         "step_type": "task", "evidence_required": [], "controls": [],
         "next": [{"target": "EL-bo", "condition": None}]},
        {"id": "EL-bo", "name": "check beneficial ownership", "sequence_hint": 5,
         "step_type": "task", "evidence_required": [], "controls": [],
         "next": [{"target": "EL-rate", "condition": None}]},
        {"id": "EL-rate", "name": "compute risk rating", "sequence_hint": 6,
         "step_type": "task", "evidence_required": [], "controls": [],
         "next": [{"target": "EL-edd", "condition": None}]},
        {"id": "EL-edd", "name": "determine edd requirement",
         "sequence_hint": 7, "step_type": "task", "evidence_required": [], "controls": [],
         "next": [{"target": "EL-decide", "condition": None}]},
        {"id": "EL-decide", "name": "final onboarding decision", "sequence_hint": 8,
         "step_type": "task", "evidence_required": [], "controls": [], "next": []},
    ],
    "deltas": [],
}

CLEAN_INDIVIDUAL = {
    "applicant_type": "individual", "full_name": "Anna Muller", "date_of_birth": "1985-04-12",
    "jurisdiction": "Germany", "jurisdiction_risk": "low", "address": "10 Maple Street",
    "id_documents": ["passport", "utility_bill"], "expected_activity_usd": 25_000,
}
BOUNDARY_ENTITY = {
    "applicant_type": "legal_entity", "full_name": "Harbor Trading Ltd",
    "jurisdiction": "Kavastan", "jurisdiction_risk": "high", "address": "1 Commerce Park",
    "id_documents": ["certificate_of_incorporation", "beneficial_ownership_certification"],
    "expected_activity_usd": 120_000,
    "beneficial_owners": [
        {"name": "R. Kovalenko", "ownership_pct": 22.0, "jurisdiction": "Kavastan",
         "jurisdiction_risk": "high"},
        {"name": "J. Smith", "ownership_pct": 52.0, "jurisdiction": "United Kingdom",
         "jurisdiction_risk": "low"},
    ],
}


class TestAuditChain:
    def test_chain_links_and_verifies(self, tmp_path):
        log = AuditLog(tmp_path / "audit.jsonl")
        e1 = log.append(case_id="C1", step_id="s1", actor="agent", event_type="atom_executed",
                        decision="approve", citations=["FFIEC-CIP-¶2"], confidence=0.9)
        e2 = log.append(case_id="C1", step_id="s2", actor="agent", event_type="atom_executed",
                        decision="approve", citations=[], confidence=0.8)
        assert e2.prev_event_hash == e1.event_hash
        assert log.verify_chain() == (True, None)

    def test_tampering_is_detectable(self, tmp_path):
        path = tmp_path / "audit.jsonl"
        log = AuditLog(path)
        log.append(case_id="C1", step_id="s1", actor="agent", event_type="atom_executed",
                   decision="approve", citations=[], confidence=0.9)
        log.append(case_id="C1", step_id="s2", actor="agent", event_type="atom_executed",
                   decision="approve", citations=[], confidence=0.9)
        lines = path.read_text(encoding="utf-8").splitlines()
        path.write_text(lines[0].replace('"approve"', '"rejected"') + "\n" + lines[1] + "\n",
                        encoding="utf-8")
        intact, problem = log.verify_chain()
        assert not intact and "altered" in problem

    def test_deletion_is_detectable(self, tmp_path):
        path = tmp_path / "audit.jsonl"
        log = AuditLog(path)
        for i in range(3):
            log.append(case_id="C1", step_id=f"s{i}", actor="agent", event_type="e",
                       decision="d", citations=[], confidence=0.9)
        lines = path.read_text(encoding="utf-8").splitlines()
        path.write_text(lines[0] + "\n" + lines[2] + "\n", encoding="utf-8")
        intact, problem = log.verify_chain()
        assert not intact and "broken link" in problem

    def test_replay_reconstructs_only_that_case(self, tmp_path):
        log = AuditLog(tmp_path / "audit.jsonl")
        log.append(case_id="C1", step_id="s1", actor="agent", event_type="e", decision="d",
                   citations=[], confidence=None)
        log.append(case_id="C2", step_id="s1", actor="agent", event_type="e", decision="d",
                   citations=[], confidence=None)
        assert [e.case_id for e in log.replay("C1")] == ["C1"]


class TestApprovalStore:
    def test_create_list_decide_roundtrip(self, tmp_path):
        store = ApprovalStore(tmp_path)
        out = AtomOutput(result={"x": 1}, citations=[Citation(clause_id="FFIEC-CIP-¶2")],
                         confidence=0.4, needs_human=True)
        rec = store.create("GC-017", "EL-bo", "confidence 0.40 < 0.7", out,
                           {"applicant": "…"})
        assert len(store.list_pending()) == 1
        decided = store.decide(rec.request.approval_id, "approve", "a.shukla", "looks fine")
        assert decided.decision.decision == "approve"
        assert store.list_pending() == []

    def test_double_decide_is_idempotent(self, tmp_path):
        store = ApprovalStore(tmp_path)
        rec = store.create("C", "S", "r", AtomOutput(result={}, confidence=0.1))
        store.decide(rec.request.approval_id, "approve", "a.shukla")
        second = store.decide(rec.request.approval_id, "reject", "someone_else")
        assert second.decision.decision == "approve"

    def test_unknown_approval_raises(self, tmp_path):
        with pytest.raises(KeyError):
            ApprovalStore(tmp_path).decide("AP-nope", "approve", "a.shukla")


class TestExecutor:
    def test_clean_case_runs_straight_through(self, tmp_path):
        spec = compile_workflow(PROCESS)
        result = execute_case(spec, "GC-003", CLEAN_INDIVIDUAL,
                              audit=AuditLog(tmp_path / "a.jsonl"))
        assert result.outcome == "approved"
        assert not result.escalated
        assert "verify_identity_documents" in result.path or "EL-verify" in result.path
        assert result.citations

    def test_boundary_case_escalates_and_never_auto_decides(self, tmp_path):
        spec = compile_workflow(PROCESS)
        result = execute_case(spec, "GC-017", BOUNDARY_ENTITY, audit=AuditLog(tmp_path / "a.jsonl"))
        assert result.escalated
        assert result.outcome == "edd_escalated"
        assert any("20" in r or "unresolved" in r for r in result.escalation_reasons)

    def test_no_reviewer_means_halt_not_approve(self, tmp_path):
        """The safety-critical default: an unattended system never approves for a human."""
        spec = compile_workflow(PROCESS)
        result = execute_case(spec, "GC-017", BOUNDARY_ENTITY, approval_resolver=None,
                              audit=AuditLog(tmp_path / "a.jsonl"))
        assert result.outcome != "approved"

    def test_approved_gate_resumes_the_case(self, tmp_path):
        spec = compile_workflow(PROCESS)
        result = execute_case(spec, "GC-017", BOUNDARY_ENTITY,
                              approval_resolver=lambda *a, **k: "approve",
                              audit=AuditLog(tmp_path / "a.jsonl"))
        assert result.escalated
        assert "EL-decide" in [r.node_id for r in result.records]

    def test_forced_hitl_gate_from_high_severity_delta(self, tmp_path):
        proc = {**PROCESS, "deltas": [{"id": "DET-001", "severity": "high",
                                       "about_element_id": "EL-verify",
                                       "description": "callback skipped below $10k"}]}
        spec = compile_workflow(proc)
        result = execute_case(spec, "GC-030", CLEAN_INDIVIDUAL, deltas=proc["deltas"],
                              approval_resolver=lambda *a, **k: "approve",
                              audit=AuditLog(tmp_path / "a.jsonl"))
        assert result.escalated
        assert any("DET-001" in r for r in result.escalation_reasons)

    def test_audit_trail_written_for_every_step(self, tmp_path):
        log = AuditLog(tmp_path / "a.jsonl")
        spec = compile_workflow(PROCESS)
        execute_case(spec, "GC-003", CLEAN_INDIVIDUAL, audit=log)
        events = log.replay("GC-003")
        assert len(events) >= 8
        assert log.verify_chain() == (True, None)


def test_determinism_check_passes():
    """The Temporal determinism rule is enforced in CI, not by memory."""
    proc = subprocess.run([sys.executable, "scripts/check_determinism.py"],
                          cwd=ROOT, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stdout + proc.stderr
