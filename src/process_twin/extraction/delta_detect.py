"""Delta detection: conflicts + mined patterns + provenance gaps -> typed Delta nodes"""

from __future__ import annotations

from pathlib import Path

import yaml

from process_twin.ingestion.case_logs import CaseLogPattern
from process_twin.schemas.process import AttributeConflict, CanonicalElement, Delta

PRESENCE_ROUTES: list[tuple[tuple[str, ...], str, str, str]] = [
    (("address mismatch",), "unwritten_rule", "medium",
     "Encode the exception: the two-mismatch EDD trigger is good control design - write it down."),
    (("renewal receipt", "expired passport"), "unwritten_rule", "medium",
     "Align policy: codify the renewal-receipt acceptance with its 30-day follow-up task."),
    (("verbal", "pep"), "unwritten_rule", "medium",
     "Retrain: formal EDD ticket first, discussion second - the trail must start on the record."),
    (("foreign tax",), "gap", "medium",
     "Align policy: write the foreign-tax-ID-only procedure the EDD specialist already runs."),
    (("tolerance", "transliterat"), "unwritten_rule", "high",
     "Fix tooling: transliteration handling belongs in the matcher, not in per-analyst overrides."),
]

PATTERN_SUPPORT = {
    "threshold:bo": "PAT-BO-SCRUTINY-BAND",
    "sequence": "PAT-SEQ-SCREEN-FIRST",
    "skipped_step:callback": "PAT-CALLBACK-SKIPPED-SMALL",
    "stricter_practice:utility": "PAT-UTILITY-BILL-60D",
    "unwritten:address mismatch": "PAT-ADDRESS-MISMATCH-REFERRAL",
    "unwritten:renewal receipt": "PAT-EXPIRED-PASSPORT-RECEIPT",
    "unwritten:verbal": "PAT-VERBAL-PEP-WALKOVER",
    "unwritten:tolerance": "PAT-MATCH-TOLERANCE-WIDENED",
    "gap:foreign tax": "PAT-FOREIGN-TAX-ID-ADHOC",
}


def _support(patterns: dict[str, CaseLogPattern], key: str) -> tuple[int, list[str]]:
    pat = patterns.get(PATTERN_SUPPORT.get(key, ""))
    return (pat.support_count, [pat.id]) if pat else (0, [])


def detect_deltas(
    canonicals: list[CanonicalElement],
    conflicts: list[AttributeConflict],
    patterns: list[CaseLogPattern],
) -> list[Delta]:
    pat_by_id = {p.id: p for p in patterns}
    deltas: list[Delta] = []

    def add(kind, severity, description, about, written, practiced, recommendation, support=0):
        deltas.append(Delta(
            id=f"DET-{len(deltas) + 1:03d}", kind=kind, severity=severity,
            description=description, about_element_id=about,
            written_view=written, practiced_view=practiced,
            recommendation=recommendation, support_count=support,
        ))

    attrs_all = {a for c in canonicals for a in c.attributes}

    for cf in sorted(conflicts, key=lambda c: (c.element_id, c.attribute)):
        written_refs = sorted({s.ref for s in cf.written_spans})
        practiced_refs = sorted({s.ref for s in cf.practiced_spans})

        if (cf.attribute == "bo_scrutiny_pct" and cf.written_value is None
                and "bo_threshold_pct" in attrs_all):
            n, pats = _support(pat_by_id, "threshold:bo")
            add("threshold", "high",
                f"Beneficial-ownership scrutiny applied from {cf.practiced_value}% for "
                "high-risk jurisdictions, below the written 25% certification threshold.",
                cf.element_id, written_refs, practiced_refs + pats,
                "Encode the exception (document the 20% high-risk practice) or align to "
                "25% and retrain - an undocumented threshold is an exam finding.", n)
            continue

        if (cf.attribute == "utility_bill_max_age_days" and cf.written_value
                and cf.practiced_value and int(cf.practiced_value) < int(cf.written_value)):
            n, pats = _support(pat_by_id, "stricter_practice:utility")
            add("stricter_practice", "low",
                f"Utility bills accepted only up to {cf.practiced_value} days in practice "
                f"vs {cf.written_value} days written.",
                cf.element_id, written_refs, practiced_refs + pats,
                "Pick one number: stricter-than-written is compliant but makes customer "
                "outcomes depend on which analyst you draw.", n)
            continue

        if cf.attribute == "callback_min_activity_usd" and cf.written_value is None:
            n, pats = _support(pat_by_id, "skipped_step:callback")
            add("skipped_step", "high",
                f"Callback verification skipped below ${cf.practiced_value} expected activity "
                "- an invented floor threshold on a written control.",
                cf.element_id, written_refs, practiced_refs + pats,
                "Retrain staff, or replace the control with a documented risk-based threshold "
                "- a rule nobody follows plus a practice nobody wrote down is the worst of both.",
                n)
            continue

        if cf.attribute == "screening_match_tolerance" and cf.written_value is None:
            n, pats = _support(pat_by_id, "unwritten:tolerance")
            add("unwritten_rule", "high",
                "Screening match tolerance manually widened for transliterated names - "
                "per-analyst overrides on a screening control.",
                cf.element_id, written_refs, practiced_refs + pats,
                "Fix tooling: transliteration support belongs in the matcher natively.", n)
            continue

        if cf.written_value and cf.practiced_value and cf.written_value != cf.practiced_value:
            add("threshold", "medium",
                f"'{cf.attribute}' diverges: written {cf.written_value} vs practiced "
                f"{cf.practiced_value} on {cf.element_name}.",
                cf.element_id, written_refs, practiced_refs,
                "Reconcile the parameter and document the chosen value.")

    for canon in canonicals:
        if canon.element_type not in {"exception", "escalation", "control"}:
            continue
        if any(s.source_type == "policy" for s in canon.provenance):
            continue
        text = f"{canon.name} {canon.description}".lower()
        for keywords, kind, severity, rec in PRESENCE_ROUTES:
            if any(k in text for k in keywords):
                key = f"{'gap' if kind == 'gap' else 'unwritten'}:{keywords[0]}"
                n, pats = _support(pat_by_id, key)
                refs = sorted({s.ref for s in canon.provenance})
                add(kind, severity,
                    f"{canon.name}: {canon.description} (no written-policy basis found).",
                    canon.id, [], refs + pats, rec, n)
                break

    if "PAT-SEQ-SCREEN-FIRST" in pat_by_id:
        screen = next((c for c in canonicals if "screen" in c.name.lower()), None)
        verify = next((c for c in canonicals if "verify" in c.name.lower()), None)
        if screen and verify:
            pat = pat_by_id["PAT-SEQ-SCREEN-FIRST"]
            add("sequence", "low",
                "Sanctions/PEP screening runs before identity verification in practice; the "
                "written flow implies verification first.",
                screen.id,
                sorted({s.ref for s in verify.provenance if s.source_type == "policy"}),
                [pat.id], "Align policy: fail-fast sequencing is defensible - update the "
                "written order to match (same controls, same evidence, better order).",
                pat.support_count)

    acc, rej = pat_by_id.get("PAT-PO-BOX-ACCEPTED"), pat_by_id.get("PAT-PO-BOX-REJECTED")
    if acc and rej:
        about = next((c.id for c in canonicals if "address" in c.name.lower()), "EL-address_policy")
        add("practitioner_conflict", "medium",
            "PO box addresses: QA rejects outright while frontline accepts with a supplemental "
            "document - same facts, opposite outcomes, policy silent.",
            about, [], [acc.id, rej.id],
            "Align policy: pick a rule. Two customers with identical facts getting different "
            "outcomes is indefensible in review.", acc.support_count + rej.support_count)

    return deltas


def score_against_ledger(
    detected: list[Delta], ledger_path: Path = Path("data/interviews/ledger.yaml")
) -> dict:
    """Greedy 1:1 match: a detected delta hits a ledger row when kinds agree and any"""
    rows = yaml.safe_load(ledger_path.read_text(encoding="utf-8"))["deltas"]
    matched: dict[str, str] = {}
    used: set[str] = set()
    for row in rows:
        for d in detected:
            if d.id in used or d.kind != row["kind"]:
                continue
            if any(kw in d.description.lower() for kw in row["keywords"]):
                matched[row["id"]] = d.id
                used.add(d.id)
                break
    tp = len(matched)
    fp = len(detected) - tp
    fn = len(rows) - tp
    return {
        "precision": tp / len(detected) if detected else 0.0,
        "recall": tp / len(rows) if rows else 0.0,
        "tp": tp, "fp": fp, "fn": fn,
        "matched": matched,
        "missed_rows": [r["id"] for r in rows if r["id"] not in matched],
        "unmatched_detected": [d.id for d in detected if d.id not in used],
    }
