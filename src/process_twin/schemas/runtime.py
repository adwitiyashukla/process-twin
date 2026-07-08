"""Runtime contracts: AtomInput/AtomOutput, Citation, ApprovalRequest (brief §7.2, §7.5).

`extra="forbid"` everywhere is deliberate: the self-correction loop (§6.1) depends on
Pydantic rejecting malformed LLM output loudly and specifically — a permissive schema
would silently swallow exactly the failures we want to catch, re-prompt on, and count.
"""

from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field, field_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Citation(StrictModel):
    """A clause the decision relied on. clause_id must map to a human-checkable location
    in the clause store — the entire citation guardrail (§7.3) hangs on that stability."""

    clause_id: str
    quote: str | None = None  # optional exact span, for the approvals UI
    relevance_score: float | None = None  # set by the citation validator's reranker pass

    @field_validator("clause_id")
    @classmethod
    def _non_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("clause_id must be non-empty")
        return v.strip()


class AtomInput(StrictModel):
    case_id: str
    step_id: str
    payload: dict = Field(default_factory=dict)  # step-specific inputs (applicant data etc.)
    context: dict = Field(default_factory=dict)  # accumulated case state from prior atoms


class AtomOutput(StrictModel):
    """Every atom returns exactly this (§7.2). Guardrails read citations/confidence;
    the compiler reads needs_human; the audit log hashes the whole object."""

    result: dict
    citations: list[Citation] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    needs_human: bool = False
    notes: str = ""


class ApprovalRequest(StrictModel):
    """A pending HITL gate (§7.5): everything a reviewer needs to decide, nothing more."""

    approval_id: str
    case_id: str
    step_id: str
    # reason examples: "confidence 0.55 < 0.7", "high-severity delta D1", "uncited decision"
    reason: str
    atom_output: AtomOutput
    # timezone.utc (not datetime.UTC): sandbox verification runs py3.10; target stays 3.11+
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)  # noqa: UP017
    )
