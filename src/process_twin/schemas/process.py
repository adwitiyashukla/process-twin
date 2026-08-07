"""Extraction and graph contracts: ProcessElement, CanonicalElement, Delta."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ElementType = Literal["step", "control", "exception", "evidence_requirement", "escalation"]
SourceType = Literal["policy", "interview", "case_log"]
Actor = Literal["human", "agent", "system"]
Severity = Literal["low", "medium", "high"]
DeltaKind = Literal[
    "threshold", "gap", "unwritten_rule", "sequence",
    "stricter_practice", "skipped_step", "practitioner_conflict",
]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SourceSpan(StrictModel):
    """Exact provenance pointer: clause_id / transcript segment id / case id / pattern id."""

    source_type: SourceType
    ref: str
    quote: str | None = None


class ProcessElement(StrictModel):
    """What every per-source extractor emits. source_spans is required, never optional."""

    element_type: ElementType
    name: str
    description: str
    actor: Actor | None = None
    preconditions: list[str] = Field(default_factory=list)
    evidence_required: list[str] = Field(default_factory=list)
    controls_referenced: list[str] = Field(default_factory=list)
    exception_triggers: list[str] = Field(default_factory=list)
    sequence_hint: int | None = None
    attributes: dict[str, str] = Field(default_factory=dict)
    source_spans: list[SourceSpan] = Field(min_length=1)
    extractor_confidence: float = Field(ge=0.0, le=1.0)


class CanonicalElement(StrictModel):
    """Post-reconciliation node: one real-world element with all provenance attached."""

    id: str
    element_type: ElementType
    name: str
    description: str
    actor: Actor | None = None
    attributes: dict[str, str] = Field(default_factory=dict)
    sequence_hint: int | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    provenance: list[SourceSpan] = Field(min_length=1)
    merged_names: list[str] = Field(default_factory=list)


class AttributeConflict(StrictModel):
    """Sources disagree on an attribute, so it becomes a delta, never averaged away."""

    element_id: str
    element_name: str
    attribute: str
    written_value: str | None
    practiced_value: str | None
    written_spans: list[SourceSpan] = Field(default_factory=list)
    practiced_spans: list[SourceSpan] = Field(default_factory=list)


class Delta(StrictModel):
    """First-class divergence node, the whole point of the project."""

    id: str
    kind: DeltaKind
    severity: Severity
    description: str
    about_element_id: str
    written_view: list[str] = Field(default_factory=list)
    practiced_view: list[str] = Field(default_factory=list)
    recommendation: str
    support_count: int = 0
