"""Temporal activities: everything non-deterministic lives HERE, never in workflow code"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from temporalio import activity

from process_twin.runtime.atoms import get_atom
from process_twin.runtime.compiler import NodeSpec
from process_twin.schemas.audit import AuditLog
from process_twin.schemas.runtime import AtomInput, AtomOutput


@dataclass
class ExecuteAtomInput:
    case_id: str
    step_id: str
    atom: str
    applicant: dict
    context: dict


@dataclass
class AuditInput:
    case_id: str
    step_id: str
    actor: str
    event_type: str
    decision: str
    citations: list[str]
    confidence: float | None = None


@activity.defn
async def execute_atom(payload: ExecuteAtomInput) -> dict:
    """Run one atom. LLM calls, clock reads and randomness are all downstream of here."""
    atom_input = AtomInput(
        case_id=payload.case_id, step_id=payload.step_id,
        payload={"applicant": payload.applicant}, context=payload.context,
    )
    output: AtomOutput = get_atom(payload.atom)(atom_input)
    return output.model_dump(mode="json")


@activity.defn
async def append_audit(payload: AuditInput) -> str:
    """Append one audit event, idempotently."""
    log = AuditLog()
    for existing in log.replay(payload.case_id):
        if existing.step_id == payload.step_id and existing.event_type == payload.event_type:
            return existing.event_hash
    event = log.append(
        case_id=payload.case_id, step_id=payload.step_id, actor=payload.actor,
        event_type=payload.event_type, decision=payload.decision,
        citations=payload.citations, confidence=payload.confidence,
    )
    return event.event_hash


@activity.defn
async def load_workflow_spec(_: str) -> dict:
    """Compile the workflow from the derived graph. An activity, because it reads disk."""
    import json

    from process_twin.runtime.compiler import compile_workflow

    derived = Path("data/derived")
    canonicals = json.loads((derived / "canonicals.json").read_text(encoding="utf-8"))
    deltas = json.loads((derived / "deltas.json").read_text(encoding="utf-8"))
    steps = [
        {"id": c["id"], "name": c["name"], "step_type": "task",
         "sequence_hint": c.get("sequence_hint"), "evidence_required": [], "controls": [],
         "next": []}
        for c in canonicals if c["element_type"] == "step"
    ]
    ordered = sorted(steps, key=lambda s: (s["sequence_hint"] is None, s["sequence_hint"] or 0))
    for a, b in zip(ordered, ordered[1:], strict=False):
        a["next"] = [{"target": b["id"], "condition": None}]
    return compile_workflow({"steps": ordered, "deltas": deltas}).model_dump(mode="json")


def node_from_dict(d: dict) -> NodeSpec:
    return NodeSpec.model_validate(d)
