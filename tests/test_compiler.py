"""Compiler contracts (§7.1). Each compile-time rule the brief names gets a test:
cycles rejected, unreachable warned, missing evidence is a compile error, high-severity
deltas force a HITL gate."""

import pytest

from process_twin.runtime.compiler import CompileError, compile_workflow


def step(id_, name, seq, nxt=None, evidence=None, controls=None, step_type="task"):
    return {"id": id_, "name": name, "sequence_hint": seq, "step_type": step_type,
            "evidence_required": evidence or [], "controls": controls or [],
            "next": nxt or []}


def linear_process(**kw):
    steps = [
        step("EL-collect", "collect customer information", 1,
             [{"target": "EL-verify", "condition": None}]),
        step("EL-verify", "verify identity documents", 2,
             [{"target": "EL-decide", "condition": None}], evidence=["passport"]),
        step("EL-decide", "final onboarding decision", 3),
    ]
    return {"steps": steps, "deltas": [], **kw}


def test_linear_process_compiles_in_sequence_order():
    spec = compile_workflow(linear_process())
    assert spec.entry == "EL-collect"
    assert [n.id for n in spec.nodes] == ["EL-collect", "EL-verify", "EL-decide"]
    assert spec.node("EL-verify").atom == "verify_identity_documents"
    assert spec.warnings == []


def test_cycle_is_rejected_with_readable_path():
    proc = linear_process()
    proc["steps"][2]["next"] = [{"target": "EL-verify", "condition": None}]
    with pytest.raises(CompileError) as exc:
        compile_workflow(proc)
    msg = str(exc.value)
    assert "cycle" in msg and "->" in msg
    assert "retry" in msg  # explains WHY v1 forbids cycles


def test_missing_evidence_is_a_compile_error_not_a_runtime_surprise():
    proc = linear_process()
    proc["steps"][1]["evidence_required"] = ["notarized_hologram"]
    with pytest.raises(CompileError) as exc:
        compile_workflow(proc)
    assert "notarized_hologram" in str(exc.value)


def test_unreachable_node_warns_but_compiles():
    proc = linear_process()
    proc["steps"].append(step("EL-orphan", "compute risk rating", 9))
    spec = compile_workflow(proc)
    assert any("unreachable" in w and "EL-orphan" in w for w in spec.warnings)
    assert spec.node("EL-orphan")  # still compiled — data-quality signal, not fatal


def test_high_severity_delta_forces_hitl_gate():
    proc = linear_process()
    proc["deltas"] = [{"id": "DET-001", "severity": "high",
                       "about_element_id": "EL-verify",
                       "description": "callback skipped below $10k"}]
    spec = compile_workflow(proc)
    gate = spec.node("EL-verify::hitl")
    assert gate.kind == "hitl" and gate.forced_hitl
    assert "DET-001" in gate.hitl_reason
    # the gate sits BETWEEN the step and its successor — it cannot be bypassed
    assert [e.target for e in spec.successors("EL-verify")] == ["EL-verify::hitl"]
    assert [e.target for e in spec.successors("EL-verify::hitl")] == ["EL-decide"]


def test_low_and_medium_deltas_do_not_force_a_gate():
    proc = linear_process()
    proc["deltas"] = [{"id": "DET-009", "severity": "low", "about_element_id": "EL-verify",
                       "description": "sequence divergence"}]
    spec = compile_workflow(proc)
    assert not any(n.kind == "hitl" for n in spec.nodes)


def test_control_inserts_guard_immediately_after_governed_step():
    proc = linear_process()
    proc["steps"][1]["controls"] = ["identity_verification_control"]
    spec = compile_workflow(proc)
    assert spec.node("EL-verify::guard").kind == "guard"
    assert [e.target for e in spec.successors("EL-verify")] == ["EL-verify::guard"]


def test_unknown_next_target_warns():
    proc = linear_process()
    proc["steps"][0]["next"] = [{"target": "EL-ghost", "condition": None}]
    spec = compile_workflow(proc)
    assert any("EL-ghost" in w for w in spec.warnings)


def test_empty_process_is_an_error():
    with pytest.raises(CompileError):
        compile_workflow({"steps": [], "deltas": []})


def test_unmapped_step_falls_back_to_recorded_note():
    proc = linear_process()
    proc["steps"].insert(1, step("EL-weird", "consult the oracle", 2,
                                 [{"target": "EL-verify", "condition": None}]))
    proc["steps"][0]["next"] = [{"target": "EL-weird", "condition": None}]
    spec = compile_workflow(proc)
    # never silently dropped from the audit trail
    assert spec.node("EL-weird").atom == "record_step_note"
