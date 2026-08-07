"""Temporal workflow: one workflow per case."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from process_twin.durability.activities import (
        AuditInput,
        ExecuteAtomInput,
        append_audit,
        execute_atom,
        load_workflow_spec,
    )

ATOM_RETRY = RetryPolicy(
    initial_interval=timedelta(seconds=2),
    backoff_coefficient=2.0,
    maximum_interval=timedelta(seconds=30),
    maximum_attempts=4,
)


@dataclass
class CaseWorkflowInput:
    case_id: str
    applicant: dict


@dataclass
class ApprovalSignal:
    decision: str
    reviewer: str
    note: str = ""


@workflow.defn(name="ProcessTwinCase")
class CaseWorkflow:
    def __init__(self) -> None:
        self._approval: ApprovalSignal | None = None
        self._current_step: str = "not_started"
        self._path: list[str] = []

    @workflow.signal
    def approval_decision(self, signal: ApprovalSignal) -> None:
        """Resume point for a human gate: the API signals here once the decision is stored."""
        self._approval = signal

    @workflow.query
    def status(self) -> dict:
        """Mid-flight state the durability demo queries either side of the kill."""
        return {"current_step": self._current_step, "path": list(self._path),
                "awaiting_human": self._approval is None and self._current_step.endswith("::hitl")}

    @workflow.run
    async def run(self, payload: CaseWorkflowInput) -> dict:
        spec = await workflow.execute_activity(
            load_workflow_spec, payload.case_id,
            start_to_close_timeout=timedelta(seconds=60), retry_policy=ATOM_RETRY,
        )
        nodes = {n["id"]: n for n in spec["nodes"]}
        edges = spec["edges"]
        context: dict = {}
        node_id = spec["entry"]
        outcome = "in_progress"

        while node_id is not None:
            node = nodes[node_id]
            self._current_step = node_id

            if node["kind"] == "atom":
                result = await workflow.execute_activity(
                    execute_atom,
                    ExecuteAtomInput(case_id=payload.case_id, step_id=node["step_id"] or node_id,
                                     atom=node["atom"], applicant=payload.applicant,
                                     context=context),
                    start_to_close_timeout=timedelta(minutes=2), retry_policy=ATOM_RETRY,
                )
                context[node["atom"]] = result["result"]
                self._path.append(node["step_id"] or node_id)
                await workflow.execute_activity(
                    append_audit,
                    AuditInput(case_id=payload.case_id, step_id=node["step_id"] or node_id,
                               actor="agent", event_type="atom_executed",
                               decision=str(result["result"])[:200],
                               citations=[c["clause_id"] for c in result["citations"]],
                               confidence=result["confidence"]),
                    start_to_close_timeout=timedelta(seconds=30), retry_policy=ATOM_RETRY,
                )
                if result["needs_human"]:
                    decision = await self._await_human(payload.case_id,
                                                       node["step_id"] or node_id)
                    if decision == "reject":
                        outcome = "rejected"
                        break
                    if decision == "request_info":
                        outcome = "pending_information"
                        break

            elif node["kind"] == "hitl":
                decision = await self._await_human(payload.case_id, node["step_id"] or node_id)
                if decision == "reject":
                    outcome = "rejected"
                    break

            successors = [e for e in edges if e["source"] == node_id]
            node_id = successors[0]["target"] if successors else None

        if outcome == "in_progress":
            outcome = context.get("final_onboarding_decision", {}).get("decision", "approved")
        return {"case_id": payload.case_id, "outcome": outcome, "path": self._path}

    async def _await_human(self, case_id: str, step_id: str) -> str:
        """Sleep until a human decides. This is the interrupt-and-resume primitive: no"""
        self._approval = None
        await workflow.execute_activity(
            append_audit,
            AuditInput(case_id=case_id, step_id=step_id, actor="system",
                       event_type="awaiting_human", decision="workflow suspended",
                       citations=[], confidence=None),
            start_to_close_timeout=timedelta(seconds=30), retry_policy=ATOM_RETRY,
        )
        await workflow.wait_condition(lambda: self._approval is not None)
        signal = self._approval
        await workflow.execute_activity(
            append_audit,
            AuditInput(case_id=case_id, step_id=step_id, actor="human",
                       event_type="approval_decision",
                       decision=f"{signal.decision} by {signal.reviewer}",
                       citations=[], confidence=None),
            start_to_close_timeout=timedelta(seconds=30), retry_policy=ATOM_RETRY,
        )
        return signal.decision


async def signal_approval(workflow_id: str, decision: str, reviewer: str, note: str = "") -> None:
    """Called by the approvals API after the decision is persisted."""
    from temporalio.client import Client

    from process_twin.config import get_settings

    settings = get_settings()
    client = await Client.connect(settings.temporal_address, namespace=settings.temporal_namespace)
    handle = client.get_workflow_handle(workflow_id)
    await handle.signal(CaseWorkflow.approval_decision,
                        ApprovalSignal(decision=decision, reviewer=reviewer, note=note))
