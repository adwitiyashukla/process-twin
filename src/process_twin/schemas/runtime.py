"""Runtime contracts: AtomInput, AtomOutput, Citation, ApprovalRequest."""

from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field, field_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Citation(StrictModel):
    """A clause the decision relied on. clause_id must map to a human-checkable location"""

    clause_id: str
    quote: str | None = None
    relevance_score: float | None = None

    @field_validator("clause_id")
    @classmethod
    def _non_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("clause_id must be non-empty")
        return v.strip()


class AtomInput(StrictModel):
    case_id: str
    step_id: str
    payload: dict = Field(default_factory=dict)
    context: dict = Field(default_factory=dict)


class AtomOutput(StrictModel):
    """Every atom returns exactly this. The guardrails read citations and confidence."""

    result: dict
    citations: list[Citation] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    needs_human: bool = False
    notes: str = ""


class ApprovalRequest(StrictModel):
    """A pending human gate: everything a reviewer needs to decide, and nothing more."""

    approval_id: str
    case_id: str
    step_id: str
    reason: str
    atom_output: AtomOutput
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)  # noqa: UP017
    )
