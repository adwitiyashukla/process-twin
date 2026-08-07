"""Case-log loader and deterministic pattern miner."""

from __future__ import annotations

import json
import re
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from process_twin.schemas.case import CaseLog

CASES_PATH = Path("data/case_logs/cases.jsonl")


class CaseLogPattern(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    pattern_description: str
    support_count: int
    case_ids: list[str] = Field(default_factory=list)


def load_cases(path: Path = CASES_PATH) -> list[CaseLog]:
    lines = path.read_text(encoding="utf-8").splitlines()
    return [CaseLog.model_validate_json(line) for line in lines if line.strip()]


def _idx(steps: list[str], name: str) -> int | None:
    return steps.index(name) if name in steps else None


def _has_exception(case: CaseLog, prefix: str) -> bool:
    return any(e.startswith(prefix) for e in case.exceptions)


def mine_patterns(cases: list[CaseLog]) -> list[CaseLogPattern]:
    rules: list[tuple[str, str, callable]] = [
        (
            "PAT-BO-SCRUTINY-BAND",
            "EDD referral for beneficial owner in the 20-25% band, high-risk jurisdiction "
            "(below the written 25% threshold)",
            lambda c: any(
                o.jurisdiction_risk == "high" and 20.0 <= o.ownership_pct < 25.0
                for o in c.applicant_profile.beneficial_owners
            ) and any("below the 25%" in e for e in c.escalations),
        ),
        (
            "PAT-SEQ-SCREEN-FIRST",
            "Sanctions/PEP screening executed before identity verification "
            "(written order implies verify first)",
            lambda c: (
                (s := _idx(c.steps_taken, "screen_sanctions_pep")) is not None
                and (v := _idx(c.steps_taken, "verify_identity_documents")) is not None
                and s < v
            ),
        ),
        (
            "PAT-CALLBACK-SKIPPED-SMALL",
            "Callback verification absent for accounts under $10k expected activity",
            lambda c: "callback_verification" not in c.steps_taken
            and c.applicant_profile.expected_activity_usd < 10_000,
        ),
        (
            "PAT-EXPIRED-PASSPORT-RECEIPT",
            "Expired passport accepted with official renewal receipt + follow-up task",
            lambda c: "passport_renewal_receipt" in c.documents_presented
            and _has_exception(c, "expired_primary_id"),
        ),
        (
            "PAT-ADDRESS-MISMATCH-REFERRAL",
            "Two address mismatches across documents -> automatic EDD referral",
            lambda c: _has_exception(c, "address_mismatch_across_documents")
            and any("address mismatch" in e.lower() for e in c.escalations),
        ),
        (
            "PAT-UTILITY-BILL-60D",
            "Utility bills older than ~60 days bounced despite the written 90-day allowance",
            lambda c: "requested fresher document" in c.analyst_notes.lower(),
        ),
        (
            "PAT-VERBAL-PEP-WALKOVER",
            "PEP close-associate cases briefed verbally to compliance before any ticket",
            lambda c: any("verbal briefing" in e.lower() for e in c.escalations),
        ),
        (
            "PAT-MATCH-TOLERANCE-WIDENED",
            "Screening match tolerance manually widened for transliterated names",
            lambda c: _has_exception(c, "screening_match_tolerance"),
        ),
        (
            "PAT-FOREIGN-TAX-ID-ADHOC",
            "Foreign-tax-ID-only applicants routed ad hoc to the EDD specialist "
            "(no written procedure)",
            lambda c: c.applicant_profile.tax_id_type == "foreign"
            and re.search(r"no written procedure", c.analyst_notes, re.I) is not None,
        ),
        (
            "PAT-PO-BOX-ACCEPTED",
            "PO-box address accepted with a supplemental document (frontline practice)",
            lambda c: _has_exception(c, "po_box_address_accepted"),
        ),
        (
            "PAT-PO-BOX-REJECTED",
            "PO-box address rejected outright at review (QA practice)",
            lambda c: _has_exception(c, "po_box_address_rejected"),
        ),
    ]

    patterns: list[CaseLogPattern] = []
    for pat_id, description, predicate in rules:
        hits = [c.case_id for c in cases if predicate(c)]
        if hits:
            patterns.append(CaseLogPattern(
                id=pat_id, pattern_description=description,
                support_count=len(hits), case_ids=hits,
            ))
    return patterns


def patterns_as_json(patterns: list[CaseLogPattern]) -> str:
    return json.dumps([p.model_dump() for p in patterns], indent=2, sort_keys=True)
