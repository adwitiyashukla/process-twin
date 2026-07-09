"""Case schemas (brief §3): ApplicantProfile, CaseInput, CaseOutcome, CaseLog.

CaseLog mirrors what a bank's case-management export would actually contain — which is
why it carries NO delta labels: ground truth lives in a sidecar file so phase-3 pattern
mining can't grade itself on leaked answers (see data/interviews/SYNTHETIC.md).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Outcome = Literal[
    "approved",
    "approved_with_conditions",
    "edd_escalated",
    "rejected",
]

JurisdictionRisk = Literal["low", "medium", "high"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class BeneficialOwner(StrictModel):
    name: str
    ownership_pct: float = Field(ge=0, le=100)
    jurisdiction: str
    jurisdiction_risk: JurisdictionRisk


class ApplicantProfile(StrictModel):
    applicant_type: Literal["individual", "legal_entity"]
    full_name: str  # individual name or legal entity name
    date_of_birth: str | None = None  # individuals only; ISO date string
    jurisdiction: str
    jurisdiction_risk: JurisdictionRisk
    address: str
    address_is_po_box: bool = False
    id_documents: list[str] = Field(default_factory=list)
    tax_id_type: Literal["domestic", "foreign", "none"] = "domestic"
    expected_activity_usd: int = Field(ge=0)
    pep_status: Literal["none", "direct", "close_associate"] = "none"
    beneficial_owners: list[BeneficialOwner] = Field(default_factory=list)  # entities only


class CaseInput(StrictModel):
    """What the runtime workflow receives (phase 4)."""

    case_id: str
    applicant: ApplicantProfile


class CaseLog(StrictModel):
    """One historical case record — data/case_logs/cases.jsonl (brief §4.3)."""

    case_id: str
    applicant_profile: ApplicantProfile
    documents_presented: list[str]
    steps_taken: list[str]  # in execution order — sequence deltas live here
    exceptions: list[str]
    escalations: list[str]
    outcome: Outcome
    analyst_notes: str  # free text — where tacit thresholds leak into the record
    duration_days: int = Field(ge=0)
