"""Approvals inbox (brief §7.5).

    GET  /approvals                 -> pending queue with full context
    GET  /approvals/{id}            -> one request
    POST /approvals/{id}/decide     -> {decision, reviewer, note}; resumes the workflow
                                       via Temporal signal when a workflow_id is attached

The signal is best-effort by design: the decision is PERSISTED FIRST, then signalled. If
Temporal is unreachable the human's decision is not lost — the worker picks it up from
the store on retry. Losing a reviewer's decision is worse than a delayed resume.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict

from process_twin.runtime.hitl import ApprovalStore

router = APIRouter()
store = ApprovalStore()


class DecideBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: Literal["approve", "reject", "request_info"]
    reviewer: str
    note: str = ""


@router.get("/approvals")
def list_approvals() -> list[dict]:
    return [r.model_dump(mode="json") for r in store.list_pending()]


@router.get("/approvals/{approval_id}")
def get_approval(approval_id: str) -> dict:
    record = store.get(approval_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"unknown approval {approval_id}")
    return record.model_dump(mode="json")


@router.post("/approvals/{approval_id}/decide")
def decide(approval_id: str, body: DecideBody) -> dict:
    try:
        record = store.decide(approval_id, body.decision, body.reviewer, body.note)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    signalled = False
    workflow_id = record.case_snapshot.get("workflow_id")
    if workflow_id:
        try:
            import asyncio

            from process_twin.durability.workflows import signal_approval

            asyncio.run(signal_approval(workflow_id, body.decision, body.reviewer, body.note))
            signalled = True
        except Exception:  # noqa: BLE001 — decision already persisted; worker retries
            signalled = False
    return {"approval_id": approval_id, "decision": body.decision,
            "workflow_signalled": signalled,
            "record": record.model_dump(mode="json")}
