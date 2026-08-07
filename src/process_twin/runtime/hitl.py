"""Human-in-the-loop gates and approval resume."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from process_twin.schemas.runtime import ApprovalRequest, AtomOutput

Decision = Literal["approve", "reject", "request_info"]
STORE_DIR = Path("data/approvals")


class ApprovalDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: Decision
    reviewer: str
    note: str = ""
    decided_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)  # noqa: UP017
    )


class ApprovalRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request: ApprovalRequest
    case_snapshot: dict = Field(default_factory=dict)
    decision: ApprovalDecision | None = None


class ApprovalStore:
    def __init__(self, directory: Path = STORE_DIR):
        self.dir = Path(directory)
        self.dir.mkdir(parents=True, exist_ok=True)

    def _path(self, approval_id: str) -> Path:
        return self.dir / f"{approval_id}.json"

    def create(self, case_id: str, step_id: str, reason: str, output: AtomOutput,
               case_snapshot: dict | None = None) -> ApprovalRecord:
        approval_id = f"AP-{uuid.uuid4().hex[:10]}"
        record = ApprovalRecord(
            request=ApprovalRequest(approval_id=approval_id, case_id=case_id,
                                    step_id=step_id, reason=reason, atom_output=output),
            case_snapshot=case_snapshot or {},
        )
        self._path(approval_id).write_text(record.model_dump_json(indent=2), encoding="utf-8")
        return record

    def get(self, approval_id: str) -> ApprovalRecord | None:
        path = self._path(approval_id)
        if not path.exists():
            return None
        return ApprovalRecord.model_validate_json(path.read_text(encoding="utf-8"))

    def list_pending(self) -> list[ApprovalRecord]:
        records = [ApprovalRecord.model_validate_json(p.read_text(encoding="utf-8"))
                   for p in sorted(self.dir.glob("AP-*.json"))]
        return [r for r in records if r.decision is None]

    def decide(self, approval_id: str, decision: Decision, reviewer: str,
               note: str = "") -> ApprovalRecord:
        record = self.get(approval_id)
        if record is None:
            raise KeyError(f"unknown approval {approval_id!r}")
        if record.decision is not None:
            return record
        record.decision = ApprovalDecision(decision=decision, reviewer=reviewer, note=note)
        self._path(approval_id).write_text(record.model_dump_json(indent=2), encoding="utf-8")
        return record

    def as_json(self) -> str:
        return json.dumps([r.model_dump(mode="json") for r in self.list_pending()], indent=2)
