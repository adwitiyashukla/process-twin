"""Runtime contract tests. Strictness is the feature under test, not an accident."""

import pytest
from pydantic import ValidationError

from process_twin.schemas.runtime import ApprovalRequest, AtomInput, AtomOutput, Citation


def test_atom_output_happy_path():
    out = AtomOutput(
        result={"decision": "approve"},
        citations=[Citation(clause_id="CFR-1010.230(b)(1)")],
        confidence=0.91,
    )
    assert out.needs_human is False
    assert out.citations[0].clause_id == "CFR-1010.230(b)(1)"


@pytest.mark.parametrize("bad", [-0.1, 1.1, 2, -5])
def test_confidence_bounds_enforced(bad):
    with pytest.raises(ValidationError):
        AtomOutput(result={}, confidence=bad)


def test_extra_fields_forbidden():
    with pytest.raises(ValidationError) as exc:
        AtomOutput(result={}, confidence=0.5, hallucinated_field="x")
    assert "hallucinated_field" in str(exc.value)


def test_citation_rejects_blank_clause_id():
    with pytest.raises(ValidationError):
        Citation(clause_id="   ")


def test_citation_strips_whitespace():
    assert Citation(clause_id=" FFIEC-CDD-¶3 ").clause_id == "FFIEC-CDD-¶3"


def test_atom_input_defaults_are_independent():
    a, b = AtomInput(case_id="c1", step_id="s1"), AtomInput(case_id="c2", step_id="s2")
    a.payload["k"] = "v"
    assert b.payload == {}


def test_approval_request_roundtrip():
    req = ApprovalRequest(
        approval_id="ap-1",
        case_id="GC-017",
        step_id="check_beneficial_ownership",
        reason="high-severity delta D1 attached",
        atom_output=AtomOutput(result={"flag": True}, confidence=0.4, needs_human=True),
    )
    restored = ApprovalRequest.model_validate_json(req.model_dump_json())
    assert restored.atom_output.confidence == 0.4
    assert restored.created_at.tzinfo is not None
