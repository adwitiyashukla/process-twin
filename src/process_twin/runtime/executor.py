"""Case executor: walks a compiled WorkflowSpec, runs atoms, applies guardrails, opens"""

from __future__ import annotations

from collections.abc import Callable

from pydantic import BaseModel, ConfigDict, Field

from process_twin.observability import tracing
from process_twin.runtime import guardrails
from process_twin.runtime.atoms import get_atom
from process_twin.runtime.compiler import NodeSpec, WorkflowSpec
from process_twin.schemas.runtime import AtomInput, AtomOutput

ApprovalResolver = Callable[[str, str, str, AtomOutput], str]


class StepRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    node_id: str
    step_id: str | None
    atom: str | None
    output: AtomOutput | None = None
    guardrail_reason: str | None = None
    guardrail_violations: list[str] = Field(default_factory=list)
    escalated: bool = False
    human_decision: str | None = None


class CaseResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str
    outcome: str
    path: list[str] = Field(default_factory=list)
    records: list[StepRecord] = Field(default_factory=list)
    escalated: bool = False
    escalation_reasons: list[str] = Field(default_factory=list)
    citations: list[str] = Field(default_factory=list)


def execute_case(
    spec: WorkflowSpec,
    case_id: str,
    applicant: dict,
    *,
    deltas: list[dict] | None = None,
    validator: guardrails.CitationValidator | None = None,
    approval_resolver: ApprovalResolver | None = None,
    audit=None,
    trace=None,
    extra_payload: dict | None = None,
) -> CaseResult:
    """Run one case to completion."""
    deltas = deltas or []
    context: dict = {}
    result = CaseResult(case_id=case_id, outcome="in_progress")
    node_id = spec.entry
    visited: set[str] = set()

    while node_id is not None:
        if node_id in visited:
            result.outcome = "error_cycle"
            break
        visited.add(node_id)
        node: NodeSpec = spec.node(node_id)

        if node.kind == "atom":
            payload = {"applicant": applicant, **(extra_payload or {})}
            atom_input = AtomInput(case_id=case_id, step_id=node.step_id or node.id,
                                   payload=payload, context=context)
            with tracing.atom_span(trace, node.atom or node.id, {"case_id": case_id}):
                output = get_atom(node.atom)(atom_input)
            record = StepRecord(node_id=node.id, step_id=node.step_id, atom=node.atom,
                                output=output)
            context[node.atom] = output.result
            result.path.append(node.atom or node.step_id or node.id)
            result.citations.extend(c.clause_id for c in output.citations)

            gr = guardrails.run_all(output, node.step_id or node.id, deltas, validator)
            record.guardrail_reason = gr.reason
            record.guardrail_violations = gr.violations
            if audit is not None:
                audit.append(case_id=case_id, step_id=node.step_id or node.id,
                             actor="agent", event_type="atom_executed",
                             decision=str(output.result)[:200],
                             citations=[c.clause_id for c in output.citations],
                             confidence=output.confidence)

            if gr.needs_human:
                record.escalated = True
                result.escalated = True
                result.escalation_reasons.append(gr.reason or "human review required")
                decision = (approval_resolver(case_id, node.step_id or node.id,
                                              gr.reason or "", output)
                            if approval_resolver else None)
                record.human_decision = decision
                if audit is not None:
                    audit.append(case_id=case_id, step_id=node.step_id or node.id,
                                 actor="human" if decision else "system",
                                 event_type="approval_decision" if decision else "escalated",
                                 decision=decision or "no_reviewer_available",
                                 citations=[], confidence=None)
                if decision is None:
                    result.outcome = "edd_escalated"
                    result.records.append(record)
                    break
                if decision == "reject":
                    result.outcome = "rejected"
                    result.records.append(record)
                    break
                if decision == "request_info":
                    result.outcome = "pending_information"
                    result.records.append(record)
                    break
            result.records.append(record)

        elif node.kind == "hitl":
            result.escalated = True
            reason = node.hitl_reason or "forced human gate"
            result.escalation_reasons.append(reason)
            last_output = next((r.output for r in reversed(result.records) if r.output), None)
            decision = (approval_resolver(case_id, node.step_id or node.id, reason,
                                          last_output or AtomOutput(result={}, confidence=0.0))
                        if approval_resolver else None)
            result.records.append(StepRecord(node_id=node.id, step_id=node.step_id, atom=None,
                                             guardrail_reason=reason, escalated=True,
                                             human_decision=decision))
            if audit is not None:
                audit.append(case_id=case_id, step_id=node.step_id or node.id,
                             actor="human" if decision else "system",
                             event_type="forced_hitl", decision=decision or "awaiting_human",
                             citations=[], confidence=None)
            if decision is None:
                result.outcome = "edd_escalated"
                break
            if decision == "reject":
                result.outcome = "rejected"
                break

        elif node.kind == "guard":
            result.records.append(StepRecord(node_id=node.id, step_id=node.step_id, atom=None))

        outs = spec.successors(node_id)
        node_id = outs[0].target if outs else None

    if result.outcome == "in_progress":
        decision = context.get("final_onboarding_decision", {}).get("decision")
        result.outcome = decision or ("edd_escalated" if result.escalated else "approved")
    if result.outcome == "edd_escalated":
        result.escalated = True
        if not result.escalation_reasons:
            reasons = context.get("determine_edd_requirement", {}).get("reasons", [])
            result.escalation_reasons.append("EDD required: " + (", ".join(reasons) or "risk"))
    result.citations = sorted(set(result.citations))
    return result
