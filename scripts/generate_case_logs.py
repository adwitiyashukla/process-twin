"""Generate the 60 synthetic historical case logs (brief §4.3) — DETERMINISTICALLY.

No randomness, no LLM: every value is derived from the case index, so regeneration is
byte-identical on any machine (enforced by test). Distribution: 35 policy-consistent /
18 tacit-pattern / 7 genuine-error. Delta support counts are hand-assigned below to
match the SYNTHETIC.md ledger exactly (also enforced by test).

Outputs:
    data/case_logs/cases.jsonl              — what a bank's case export would contain
    data/case_logs/ground_truth_tags.json   — sidecar labels (category, deltas, stances)
    data/case_logs/delta_support.json       — computed support counts per delta

Ground truth is sidecar-only on purpose: the phase-3 extractor mines cases.jsonl and
must never see labels (data/interviews/SYNTHETIC.md explains why).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, "src")  # runnable as a plain script from repo root

from process_twin.schemas.case import ApplicantProfile, BeneficialOwner, CaseLog  # noqa: E402

OUT_DIR = Path("data/case_logs")

FIRST = ["Anna", "Rahul", "Wei", "Sofia", "James", "Amara", "Diego", "Yuki", "Omar", "Lena",
         "Peter", "Ines", "Noah", "Grace", "Arjun", "Mia", "Tomas", "Zara", "Felix", "Nadia"]
LAST = ["Muller", "Sharma", "Chen", "Rossi", "Walker", "Okonkwo", "Alvarez", "Tanaka",
        "Haddad", "Novak", "Berg", "Costa", "Kim", "Osei", "Iyer", "Fischer", "Silva",
        "Nowak", "Andersen", "Farouk"]
ENTITY_STEMS = ["Harbor", "Northfield", "Bluepine", "Cedarline", "Quartz", "Beacon",
                "Latitude", "Ironbridge", "Silverbirch", "Crestway"]
ENTITY_KINDS = ["Trading Ltd", "Logistics LLC", "Consulting GmbH", "Holdings Ltd",
                "Imports LLC", "Services Ltd"]
# Low-risk jurisdictions are real; HIGH-RISK ONES ARE FICTIONAL by design (SYNTHETIC.md)
LOW = [("United States", "low"), ("United Kingdom", "low"), ("Canada", "low"),
       ("Germany", "low"), ("Japan", "low")]
MED = [("Portugal", "medium"), ("Chile", "medium")]
HIGH = [("Kavastan", "high"), ("Zubaria", "high"), ("Port Meridian", "high")]

# Written-policy execution order (D4 = screen moved before verify; D6 = callback absent)
S_COLLECT = "collect_customer_information"
S_VERIFY = "verify_identity_documents"
S_CALLBACK = "callback_verification"
S_SCREEN = "screen_sanctions_pep"
S_JURIS = "assess_jurisdiction_risk"
S_BO = "check_beneficial_ownership"
S_RATE = "compute_risk_rating"
S_EDD_REQ = "determine_edd_requirement"
S_EDD = "edd_review"
S_DECIDE = "final_onboarding_decision"

# Tacit-case delta assignments — hand-fixed so support counts hit the ledger exactly.
# ("r"/"a" = D10 reject/accept stance)
TACIT = [
    ["D1", "D10r"], ["D1", "D8", "D4"], ["D1", "D9", "D7"], ["D1", "D6"],
    ["D1", "D2", "D5"], ["D1", "D10a"], ["D1", "D8"], ["D1", "D6", "D4"],
    ["D1", "D9", "D8"], ["D1", "D2"], ["D1", "D7"],
    ["D2", "D3", "D5"], ["D2", "D6", "D10a"], ["D2", "D3"], ["D3", "D6", "D4"],
    ["D3", "D8", "D6"], ["D3", "D9", "D6"], ["D7", "D10r"],
]
# Policy-consistent cases carrying compliant-but-telling traces (stricter/sequence
# practices do not violate written policy — SYNTHETIC.md explains the nuance)
CONSISTENT_D4 = {4, 11, 18, 25, 32}   # screening-first ordering
CONSISTENT_D5 = {2, 8, 20, 27}        # 60-day utility-bill strictness in notes
ERROR_KINDS = [
    "identity_verification_skipped_then_approved",
    "bo_certification_never_collected",
    "sanctions_screen_run_after_decision",
    "edd_required_but_not_performed",
    "callback_skipped_on_50k_account",
    "approved_despite_two_address_mismatches",
    "pep_hit_dispositioned_without_compliance_signoff",
]


def _name(i: int) -> str:
    return f"{FIRST[i % len(FIRST)]} {LAST[(i * 7 + 3) % len(LAST)]}"


def _entity(i: int) -> str:
    return f"{ENTITY_STEMS[i % len(ENTITY_STEMS)]} {ENTITY_KINDS[(i * 3 + 1) % len(ENTITY_KINDS)]}"


def _dob(i: int) -> str:
    return f"{1958 + (i * 13) % 40}-{1 + (i * 5) % 12:02d}-{1 + (i * 11) % 28:02d}"


def _steps(entity: bool, d4: bool, d6_skip_callback: bool, edd: bool) -> list[str]:
    head = [S_COLLECT, S_SCREEN, S_VERIFY] if d4 else [S_COLLECT, S_VERIFY]
    if not d6_skip_callback:
        head.append(S_CALLBACK)
    if not d4:
        head.append(S_SCREEN)
    tail = [S_JURIS] + ([S_BO] if entity else []) + [S_RATE, S_EDD_REQ]
    if edd:
        tail.append(S_EDD)
    return head + tail + [S_DECIDE]


def _base_docs(entity: bool) -> list[str]:
    if entity:
        return ["certificate_of_incorporation", "beneficial_ownership_certification",
                "director_passport", "proof_of_business_address"]
    return ["passport", "utility_bill"]


def build_consistent(i: int) -> tuple[CaseLog, dict]:
    """35 cases exhibiting written-policy behavior (some with compliant D4/D5 traces)."""
    entity = i % 5 in (1, 3)  # 14 of 35
    juris = (LOW + MED)[i % 7]
    d4 = i in CONSISTENT_D4
    d5 = i in CONSISTENT_D5
    high_bo_case = entity and i % 7 == 3  # a few legit >=25% high-risk BOs -> clean EDD
    bo = []
    if entity:
        bo_j = HIGH[i % 3] if high_bo_case else juris
        bo = [BeneficialOwner(name=_name(i + 40), ownership_pct=100.0 if i % 3 else 51.0,
                              jurisdiction=bo_j[0], jurisdiction_risk=bo_j[1])]
    edd = high_bo_case
    profile = ApplicantProfile(
        applicant_type="legal_entity" if entity else "individual",
        full_name=_entity(i) if entity else _name(i),
        date_of_birth=None if entity else _dob(i),
        jurisdiction=juris[0], jurisdiction_risk=juris[1],
        address=f"{100 + i} {'Commerce Park' if entity else 'Maple Street'}, {juris[0]}",
        id_documents=_base_docs(entity), expected_activity_usd=12_000 + (i * 3_700) % 180_000,
        beneficial_owners=bo,
    )
    notes = "Standard onboarding; all documents verified per procedure."
    exceptions: list[str] = []
    if d5:
        notes = ("Utility bill dated 72 days ago — requested fresher document per senior "
                 "team practice (written policy accepts up to 90 days). Fresh bill received.")
        exceptions.append("proof_of_address_refresh_requested")
    if d4:
        notes += " Screening completed at intake ahead of document verification (team sequencing)."
    if edd:
        notes += " Beneficial owner >=25% in high-risk jurisdiction; EDD per written trigger."
    outcome = "edd_escalated" if edd else ("approved_with_conditions" if i % 9 == 5 else "approved")
    case = CaseLog(
        case_id=f"HC-{i + 1:03d}", applicant_profile=profile,
        documents_presented=_base_docs(entity),
        steps_taken=_steps(entity, d4, False, edd),
        exceptions=exceptions,
        escalations=(["EDD referral — beneficial owner at/above 25% in high-risk jurisdiction"]
                     if edd else []),
        outcome=outcome, analyst_notes=notes, duration_days=2 + (i * 5) % 9 + (9 if edd else 0),
    )
    deltas = (["D4"] if d4 else []) + (["D5"] if d5 else [])
    return case, {"category": "policy_consistent", "deltas": deltas}


def build_tacit(t: int) -> tuple[CaseLog, dict]:
    """18 cases statistically supporting the tacit deltas (indices 35..52)."""
    i = 35 + t
    tags = TACIT[t]
    has = lambda d: d in tags  # noqa: E731
    d10 = next((x for x in tags if x.startswith("D10")), None)
    entity = has("D1")  # all D1 cases are legal entities in high-risk jurisdictions
    juris = HIGH[t % 3] if has("D1") else (LOW + MED)[t % 7]

    bo, docs = [], _base_docs(entity)
    exceptions, escalations = [], []
    notes_parts = []

    if has("D1"):
        pct = 20.5 + (t % 9) * 0.5  # 20.5–24.5: below the written 25% line
        bo_name = _name(i + 40)
        if has("D8"):
            bo_name = ["Yevgeniy Kovalenko", "Aleksandr Petrossian", "Mikhail Tsarenko",
                       "Oleksii Zhadan"][t % 4]
        bo = [BeneficialOwner(name=bo_name, ownership_pct=pct, jurisdiction=juris[0],
                              jurisdiction_risk="high"),
              BeneficialOwner(name=_name(i + 41), ownership_pct=round(100 - pct - 26.0, 1),
                              jurisdiction="United Kingdom", jurisdiction_risk="low")]
        escalations.append(f"EDD referral — beneficial owner at {pct}% in {juris[0]} "
                           "(below the 25% certification threshold)")
        notes_parts.append(f"Owner at {pct}% in {juris[0]}: below the written 25% line, but "
                           "house practice is full scrutiny from 20% for high-risk jurisdictions.")
    if has("D2"):
        docs = [d for d in docs if d != "passport"]
        docs += ["expired_passport", "passport_renewal_receipt"]
        exceptions.append("expired_primary_id_accepted_with_renewal_receipt")
        notes_parts.append("Passport expired; official renewal receipt accepted per floor "
                           "practice with 30-day follow-up task to collect the new passport.")
    if has("D3"):
        exceptions.append("address_mismatch_across_documents_x2")
        escalations.append("EDD referral — two address mismatches across documents (house rule)")
        notes_parts.append("Two address mismatches across documents — automatic EDD referral "
                           "per unwritten team rule.")
    if has("D5"):
        exceptions.append("proof_of_address_refresh_requested")
        notes_parts.append("Utility bill dated 72 days ago — requested fresher document per "
                           "senior team practice (written policy accepts up to 90 days).")
    if has("D6"):
        notes_parts.append("Callback verification not performed: expected activity below $10k "
                           "(informal floor threshold).")
    if has("D7"):
        escalations.append("Verbal briefing to BSA compliance officer (no ticket) — "
                           "PEP close-associate; formal EDD ticket filed after discussion")
        notes_parts.append("PEP close-associate handled via verbal walk-over to compliance "
                           "before the formal ticket, per team custom.")
    if has("D8"):
        exceptions.append("screening_match_tolerance_manually_widened")
        notes_parts.append("Name appears transliterated; screening re-run with manually "
                           "widened match tolerance per senior practice.")
    if has("D9"):
        notes_parts.append("Applicant presents foreign tax ID only — no written procedure; "
                           "routed ad hoc to EDD specialist for review.")
    if d10 == "D10r":
        exceptions.append("po_box_address_rejected_at_review")
        notes_parts.append("PO-box address rejected at QA review; physical-address proof "
                           "demanded (policy silent — reviewer practice).")
    if d10 == "D10a":
        docs.append("supplemental_address_document")
        exceptions.append("po_box_address_accepted_with_supplemental_document")
        notes_parts.append("PO-box address accepted with supplemental document tying applicant "
                           "to physical location (policy silent — frontline practice).")

    profile = ApplicantProfile(
        applicant_type="legal_entity" if entity else "individual",
        full_name=_entity(i) if entity else _name(i),
        date_of_birth=None if entity else _dob(i),
        jurisdiction=juris[0], jurisdiction_risk=juris[1],
        address=(f"PO Box {200 + t}, {juris[0]}" if d10 else
                 f"{100 + i} {'Commerce Park' if entity else 'Maple Street'}, {juris[0]}"),
        address_is_po_box=bool(d10),
        id_documents=docs,
        tax_id_type="foreign" if has("D9") else "domestic",
        expected_activity_usd=(4_000 + (t * 450) % 5_500) if has("D6") else 30_000 + t * 6_500,
        pep_status="close_associate" if has("D7") else "none",
        beneficial_owners=bo,
    )
    edd = bool(escalations)
    outcome = ("rejected" if d10 == "D10r" else ("edd_escalated" if edd else
               "approved_with_conditions" if has("D2") else "approved"))
    case = CaseLog(
        case_id=f"HC-{i + 1:03d}", applicant_profile=profile, documents_presented=docs,
        steps_taken=_steps(entity, has("D4"), has("D6"), edd and d10 != "D10r"),
        exceptions=exceptions, escalations=escalations, outcome=outcome,
        analyst_notes=" ".join(notes_parts),
        duration_days=3 + (t * 7) % 11 + (9 if edd else 0),
    )
    gt = {
        "category": "tacit_pattern",
        "deltas": [x[:3] if x.startswith("D10") else x for x in tags],
    }
    if d10:
        gt["d10_stance"] = "reject" if d10 == "D10r" else "accept"
    return case, gt


def build_error(e: int) -> tuple[CaseLog, dict]:
    """7 genuine-error cases (indices 53..59) — mistakes, NOT patterns; never delta-tagged."""
    i = 53 + e
    kind = ERROR_KINDS[e]
    entity = kind == "bo_certification_never_collected"
    juris = HIGH[e % 3] if kind == "edd_required_but_not_performed" else LOW[e % 5]
    docs = _base_docs(entity)
    steps = _steps(entity, False, False, False)
    exceptions, escalations = [], []
    notes = ""
    outcome = "approved"

    if kind == "identity_verification_skipped_then_approved":
        steps = [s for s in steps if s != S_VERIFY]
        notes = ("File approved without documentary verification on record — error caught "
                 "later by QA sample.")
    elif kind == "bo_certification_never_collected":
        docs = [d for d in docs if d != "beneficial_ownership_certification"]
        steps = [s for s in steps if s != S_BO]
        notes = ("Legal entity onboarded without beneficial ownership certification — "
                 "remediation opened.")
    elif kind == "sanctions_screen_run_after_decision":
        steps = [s for s in steps if s != S_SCREEN] + [S_SCREEN]
        notes = ("Screening executed after the final decision due to queue mix-up — "
                 "retroactive clear.")
    elif kind == "edd_required_but_not_performed":
        notes = (f"High-risk jurisdiction ({juris[0]}) risk rating mandated EDD; "
                 "no EDD review on file.")
    elif kind == "callback_skipped_on_50k_account":
        steps = [s for s in steps if s != S_CALLBACK]
        notes = ("Callback verification missing on a $50k expected-activity account — "
                 "outside any informal threshold; plain miss.")
    elif kind == "approved_despite_two_address_mismatches":
        exceptions.append("address_mismatch_across_documents_x2")
        notes = ("Two address mismatches noted at intake; file approved with no referral — "
                 "contrary to both policy intent and floor practice.")
    elif kind == "pep_hit_dispositioned_without_compliance_signoff":
        exceptions.append("pep_screening_hit")
        notes = "Direct PEP match dispositioned by analyst alone; compliance sign-off absent."

    profile = ApplicantProfile(
        applicant_type="legal_entity" if entity else "individual",
        full_name=_entity(i) if entity else _name(i),
        date_of_birth=None if entity else _dob(i),
        jurisdiction=juris[0], jurisdiction_risk=juris[1],
        address=f"{100 + i} Maple Street, {juris[0]}",
        id_documents=docs,
        expected_activity_usd=50_000 if kind == "callback_skipped_on_50k_account"
        else 15_000 + e * 4_000,
        pep_status="direct" if kind.startswith("pep") else "none",
        beneficial_owners=[BeneficialOwner(name=_name(i + 40), ownership_pct=100.0,
                                           jurisdiction=juris[0], jurisdiction_risk=juris[1])]
        if entity and kind != "bo_certification_never_collected" else [],
    )
    case = CaseLog(
        case_id=f"HC-{i + 1:03d}", applicant_profile=profile, documents_presented=docs,
        steps_taken=steps, exceptions=exceptions, escalations=escalations,
        outcome=outcome, analyst_notes=notes, duration_days=2 + (e * 3) % 8,
    )
    return case, {"category": "error", "deltas": [], "error_kind": kind}


def generate() -> tuple[list[CaseLog], dict[str, dict]]:
    cases, tags = [], {}
    for i in range(35):
        c, t = build_consistent(i)
        cases.append(c)
        tags[c.case_id] = t
    for t_idx in range(18):
        c, t = build_tacit(t_idx)
        cases.append(c)
        tags[c.case_id] = t
    for e in range(7):
        c, t = build_error(e)
        cases.append(c)
        tags[c.case_id] = t
    return cases, tags


def support_counts(tags: dict[str, dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for t in tags.values():
        for d in t["deltas"]:
            counts[d] = counts.get(d, 0) + 1
    stances = [t.get("d10_stance") for t in tags.values() if t.get("d10_stance")]
    counts["D10_reject"] = stances.count("reject")
    counts["D10_accept"] = stances.count("accept")
    return dict(sorted(counts.items()))


def write_outputs(out_dir: Path = OUT_DIR) -> dict[str, int]:
    cases, tags = generate()
    out_dir.mkdir(parents=True, exist_ok=True)
    with (out_dir / "cases.jsonl").open("w", encoding="utf-8", newline="\n") as f:
        for c in cases:
            f.write(json.dumps(c.model_dump(), ensure_ascii=False, sort_keys=True) + "\n")
    (out_dir / "ground_truth_tags.json").write_text(
        json.dumps(tags, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8"
    )
    counts = support_counts(tags)
    (out_dir / "delta_support.json").write_text(
        json.dumps(counts, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return counts


def main() -> int:
    counts = write_outputs()
    cats = {}
    _, tags = generate()
    for t in tags.values():
        cats[t["category"]] = cats.get(t["category"], 0) + 1
    print(f"Wrote 60 cases -> {OUT_DIR}/cases.jsonl")
    print(f"  categories: {cats}")
    print(f"  delta support: {counts}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
