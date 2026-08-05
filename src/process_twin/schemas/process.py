"""Extraction/graph contracts: ProcessElement, CanonicalElement, Delta (brief §5, §6.1).

Every extractor (policy / interview / case log) emits the SAME ProcessElement shape —
that single contract is what makes three very different sources reconcilable. Attributes
carry tacit thresholds as strings ("bo_scrutiny_pct": "20") so schema stays stable while
the attribute vocabulary grows.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ElementType = Literal["step", "control", "exception", "evidence_requirement", "escalation"]
SourceType = Literal["policy", "interview", "case_log"]
Actor = Literal["human", "agent", "system"]
Severity = Literal["low", "medium", "high"]
# The seven delta kinds are the §5 closed set — SYNTHETIC.md's prose kinds map onto these
# (D2 "undocumented acceptance" -> unwritten_rule, D8 "tooling workaround" -> unwritten_rule…)
DeltaKind = Literal[
    "threshold", "gap", "unwritten_rule", "sequence",
    "stricter_practice", "skipped_step", "practitioner_conflict",
]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SourceSpan(StrictModel):
    """Exact provenance pointer: clause_id / transcript segment id / case id / pattern id."""

    source_type: SourceType
    ref: str  # e.g. "CFR-1010.230(b)(1)", "P1-S3", "HC-041", "PAT-SEQ-SCREEN-FIRST"
    quote: str | None = None


class ProcessElement(StrictModel):
    """What every per-source extractor emits (§6.1). source_spans is the non-negotiable:
    an element with no provenance cannot enter the graph (loader enforces it too)."""

    element_type: ElementType
    name: str
    description: str
    actor: Actor | None = None
    preconditions: list[str] = Field(default_factory=list)
    evidence_required: list[str] = Field(default_factory=list)
    controls_referenced: list[str] = Field(default_factory=list)
    exception_triggers: list[str] = Field(default_factory=list)
    sequence_hint: int | None = None  # order within its source, for sequence-delta detection
    attributes: dict[str, str] = Field(default_factory=dict)  # thresholds, limits, params
    source_spans: list[SourceSpan] = Field(min_length=1)
    extractor_confidence: float = Field(ge=0.0, le=1.0)


class CanonicalElement(StrictModel):
    """Post-reconciliation node: one real-world element, ALL provenance attached (§6.2)."""

    id: str
    element_type: ElementType
    name: str
    description: str
    actor: Actor | None = None
    attributes: dict[str, str] = Field(default_factory=dict)  # written value wins conflicts
    sequence_hint: int | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    provenance: list[SourceSpan] = Field(min_length=1)
    merged_names: list[str] = Field(default_factory=list)  # aliases from other sources


class AttributeConflict(StrictModel):
    """Sources disagree on an attribute -> delta candidate (never averaged away, §6.2)."""

    element_id: str
    element_name: str
    attribute: str
    written_value: str | None
    practiced_value: str | None
    written_spans: list[SourceSpan] = Field(default_factory=list)
    practiced_spans: list[SourceSpan] = Field(default_factory=list)


class Delta(StrictModel):
    """First-class divergence node (§5) — the thesis of the project."""

    id: str
    kind: DeltaKind
    severity: Severity
    description: str
    about_element_id: str
    written_view: list[str] = Field(default_factory=list)  # clause_ids
    practiced_view: list[str] = Field(default_factory=list)  # segment/pattern refs
    recommendation: str
    support_count: int = 0  # from case-log patterns: "seen in N of 60 historical cases"
