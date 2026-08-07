"""Atom contract + registry (brief §7.2), plus the phase-0 hello-world atom."""

from __future__ import annotations

import json
from collections.abc import Callable

from process_twin.config import get_settings
from process_twin.observability import tracing
from process_twin.schemas.runtime import AtomInput, AtomOutput, Citation

AtomFn = Callable[[AtomInput], AtomOutput]
_REGISTRY: dict[str, AtomFn] = {}


def register_atom(name: str) -> Callable[[AtomFn], AtomFn]:
    def deco(fn: AtomFn) -> AtomFn:
        if name in _REGISTRY:
            raise ValueError(f"atom {name!r} already registered")
        _REGISTRY[name] = fn
        return fn

    return deco


def get_atom(name: str) -> AtomFn:
    try:
        return _REGISTRY[name]
    except KeyError:
        raise KeyError(f"unknown atom {name!r}; registered: {sorted(_REGISTRY)}") from None


HELLO_SYSTEM = (
    "You are a component self-test inside a KYC onboarding workflow. "
    "Reply with ONLY a JSON object: "
    '{"greeting": "<one short sentence greeting the operator>", "confidence": <float 0..1>}'
)


def run_hello_atom(dry_run: bool = False, trace=None) -> tuple[AtomOutput, float]:
    """Phase-0 acceptance atom. Returns (validated output, estimated cost in USD)."""
    settings = get_settings()
    atom_input = AtomInput(case_id="CASE-HELLO", step_id="hello_world", payload={})

    with tracing.atom_span(trace, "hello_world", atom_input.model_dump()) as span:
        if dry_run:
            raw = json.dumps(
                {
                    "greeting": "Hello from process-twin (dry run - no model called).",
                    "confidence": 0.99,
                }
            )
            in_tok, out_tok = 0, 0
        else:
            import anthropic

            client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
            msg = client.messages.create(
                model=settings.model_fast,
                max_tokens=200,
                system=HELLO_SYSTEM,
                messages=[{"role": "user", "content": "Run the self-test."}],
            )
            raw = msg.content[0].text
            in_tok, out_tok = msg.usage.input_tokens, msg.usage.output_tokens

        parsed = json.loads(raw)
        output = AtomOutput(
            result={"greeting": parsed["greeting"]},
            citations=[],
            confidence=float(parsed["confidence"]),
            needs_human=False,
            notes="phase-0 hello atom: proves model call -> schema validation -> traced cost",
        )
        cost = tracing.log_generation(
            span,
            name="hello_world.completion",
            model=settings.model_fast if not dry_run else "dry-run",
            input_payload=HELLO_SYSTEM,
            output_payload=raw,
            input_tokens=in_tok,
            output_tokens=out_tok,
        )
    return output, cost


from process_twin.schemas.case import ApplicantProfile  # noqa: E402

BO_CERTIFICATION_PCT = 25.0
HIGH_RISK_JURISDICTION_RISK = "high"

CLAUSES = {
    "cip_identifiers": "FFIEC-CIP-¶1",
    "cip_documentary": "FFIEC-CIP-¶2",
    "cip_nondocumentary": "FFIEC-CIP-¶3",
    "cdd_risk_profile": "FFIEC-CDD-¶1",
    "cdd_edd": "FFIEC-CDD-¶2",
    "bo_threshold": "CFR-1010.230(b)(1)",
    "bo_control": "CFR-1010.230(d)(2)",
}


def _profile(inp: AtomInput) -> ApplicantProfile:
    return ApplicantProfile.model_validate(inp.payload["applicant"])


def _out(result, citations, confidence, needs_human=False, notes="") -> AtomOutput:
    return AtomOutput(
        result=result,
        citations=[Citation(clause_id=c) for c in citations],
        confidence=confidence, needs_human=needs_human, notes=notes,
    )


@register_atom("collect_customer_information")
def collect_customer_information(inp: AtomInput) -> AtomOutput:
    p = _profile(inp)
    required = ["full_name", "jurisdiction", "address"] + (
        [] if p.applicant_type == "legal_entity" else ["date_of_birth"]
    )
    missing = [f for f in required if not getattr(p, f, None)]
    if p.tax_id_type == "foreign":
        return _out({"collected": not missing, "missing_identifiers": missing,
                     "issue": "foreign_tax_id_only_no_written_procedure"},
                    [CLAUSES["cip_identifiers"]], 0.4, needs_human=True,
                    notes="applicant presents a foreign tax ID only: written policy has no "
                          "procedure for this (documented gap) -> human decides")
    return _out({"collected": not missing, "missing_identifiers": missing},
                [CLAUSES["cip_identifiers"]], 0.99 if not missing else 0.6,
                needs_human=bool(missing),
                notes="core identifiers per CIP" if not missing else f"missing: {missing}")


@register_atom("verify_identity_documents")
def verify_identity_documents(inp: AtomInput) -> AtomOutput:
    p = _profile(inp)
    docs = set(p.id_documents)
    primary = {"passport", "drivers_license", "national_id", "director_passport",
               "certificate_of_incorporation"}
    has_primary = bool(docs & primary)
    expired_with_receipt = "expired_passport" in docs and "passport_renewal_receipt" in docs
    po_box = p.address_is_po_box

    integrity = [sig for sig in p.risk_signals
                 if sig in {"document_tamper_indicators", "identity_inconsistency"}]
    if integrity:
        return _out({"verified": False, "issue": integrity[0]},
                    [CLAUSES["cip_documentary"]], 0.9, needs_human=True,
                    notes=f"document/identity integrity signal ({', '.join(integrity)}): "
                          "verification cannot be relied on -> human decides")
    if has_primary and not po_box:
        return _out({"verified": True, "method": "documentary"},
                    [CLAUSES["cip_documentary"]], 0.93, notes="unexpired primary ID on file")
    if expired_with_receipt:
        return _out({"verified": False, "method": "documentary",
                     "issue": "expired_primary_id_with_renewal_receipt"},
                    [CLAUSES["cip_documentary"]], 0.45, needs_human=True,
                    notes="expired primary ID + renewal receipt: written policy silent "
                          "(floor practice accepts with 30-day follow-up) -> human decides")
    if po_box:
        return _out({"verified": False, "issue": "po_box_address"},
                    [CLAUSES["cip_documentary"]], 0.4, needs_human=True,
                    notes="PO-box address: unresolved practitioner conflict -> human decides")
    return _out({"verified": False, "issue": "no_primary_identity_document"},
                [CLAUSES["cip_documentary"], CLAUSES["cip_nondocumentary"]], 0.8,
                needs_human=True, notes="no acceptable primary ID presented")


@register_atom("callback_verification")
def callback_verification(inp: AtomInput) -> AtomOutput:
    """Written control with no activity-based exemption (the D6 divergence). The atom"""
    p = _profile(inp)
    return _out({"callback_performed": True,
                 "expected_activity_usd": p.expected_activity_usd},
                [CLAUSES["cip_nondocumentary"]], 0.9,
                notes="callback performed per written control (no written $ exemption)")


@register_atom("screen_sanctions_pep")
def screen_sanctions_pep(inp: AtomInput) -> AtomOutput:
    p = _profile(inp)
    hits = list(inp.payload.get("screening_hits", []))
    hits += [sig for sig in p.risk_signals
             if sig in {"adverse_media", "sanctions_match", "structuring_pattern",
                        "rapid_resubmission", "purpose_activity_mismatch"}]
    if p.pep_status == "direct":
        hits.append("pep_direct_match")
    elif p.pep_status == "close_associate":
        hits.append("pep_close_associate")
    clean = not hits
    return _out({"screening_hits": hits, "clean": clean},
                [CLAUSES["cdd_edd"]], 0.95 if clean else 0.75,
                needs_human=("pep_direct_match" in hits or "sanctions_match" in hits),
                notes="no list hits" if clean else f"hits: {hits}")


@register_atom("assess_jurisdiction_risk")
def assess_jurisdiction_risk(inp: AtomInput) -> AtomOutput:
    p = _profile(inp)
    owner_risks = [o.jurisdiction_risk for o in p.beneficial_owners]
    highest = "high" if ("high" in [p.jurisdiction_risk, *owner_risks]) else (
        "medium" if "medium" in [p.jurisdiction_risk, *owner_risks] else "low"
    )
    return _out({"jurisdiction_risk": highest, "entity_jurisdiction": p.jurisdiction},
                [CLAUSES["cdd_risk_profile"]], 0.92,
                notes=f"highest jurisdiction risk across applicant and owners: {highest}")


@register_atom("check_beneficial_ownership")
def check_beneficial_ownership(inp: AtomInput) -> AtomOutput:
    """The D1 boundary lives here. Written rule: identify owners at >= 25%. Practice"""
    p = _profile(inp)
    if p.applicant_type != "legal_entity":
        return _out({"applicable": False}, [CLAUSES["bo_threshold"]], 0.99,
                    notes="individual applicant: beneficial ownership not applicable")

    certified = [o for o in p.beneficial_owners if o.ownership_pct >= BO_CERTIFICATION_PCT]
    band = [o for o in p.beneficial_owners
            if 20.0 <= o.ownership_pct < BO_CERTIFICATION_PCT
            and o.jurisdiction_risk == HIGH_RISK_JURISDICTION_RISK]
    has_cert = "beneficial_ownership_certification" in p.id_documents

    result = {
        "applicable": True,
        "owners_at_or_above_threshold": [o.name for o in certified],
        "owners_in_20_25_band_high_risk": [o.name for o in band],
        "certification_on_file": has_cert,
    }
    if band:
        return _out(result, [CLAUSES["bo_threshold"]], 0.5, needs_human=True,
                    notes=f"owner(s) at {[o.ownership_pct for o in band]}% in a high-risk "
                          "jurisdiction: below the written 25% line but inside the "
                          "undocumented 20% scrutiny practice -> unresolved, human decides")
    if certified and not has_cert:
        return _out(result, [CLAUSES["bo_threshold"], CLAUSES["bo_control"]], 0.85,
                    needs_human=True, notes="owner at/above 25% without certification on file")
    return _out(result, [CLAUSES["bo_threshold"]], 0.9,
                notes="beneficial ownership satisfied per written threshold")


@register_atom("compute_risk_rating")
def compute_risk_rating(inp: AtomInput) -> AtomOutput:
    """Deterministic additive scoring - an examiner can re-derive it by hand."""
    p = _profile(inp)
    ctx = inp.context
    score = 0
    factors = []
    jrisk = ctx.get("assess_jurisdiction_risk", {}).get("jurisdiction_risk", p.jurisdiction_risk)
    if jrisk == "high":
        score += 3
        factors.append("high_risk_jurisdiction")
    elif jrisk == "medium":
        score += 1
        factors.append("medium_risk_jurisdiction")
    if p.pep_status == "direct":
        score += 3
        factors.append("pep_direct")
    elif p.pep_status == "close_associate":
        score += 2
        factors.append("pep_close_associate")
    if p.expected_activity_usd >= 250_000:
        score += 1
        factors.append("high_expected_activity")
    if p.applicant_type == "legal_entity" and len(p.beneficial_owners) > 2:
        score += 1
        factors.append("complex_ownership")
    if ctx.get("screen_sanctions_pep", {}).get("screening_hits"):
        score += 2
        factors.append("screening_hits")
    if p.tax_id_type == "foreign":
        score += 1
        factors.append("foreign_tax_id_only")
    behavioural = [sig for sig in p.risk_signals
                   if sig in {"structuring_pattern", "rapid_resubmission",
                              "purpose_activity_mismatch", "adverse_media"}]
    if behavioural:
        score += 2 * len(behavioural)
        factors.extend(behavioural)
    rating = "high" if score >= 4 else ("medium" if score >= 2 else "low")
    return _out({"risk_score": score, "risk_rating": rating, "factors": factors},
                [CLAUSES["cdd_risk_profile"]], 0.9,
                notes=f"score {score} -> {rating} (factors: {factors})")


@register_atom("determine_edd_requirement")
def determine_edd_requirement(inp: AtomInput) -> AtomOutput:
    ctx = inp.context
    rating = ctx.get("compute_risk_rating", {}).get("risk_rating", "low")
    hits = ctx.get("screen_sanctions_pep", {}).get("screening_hits", [])
    bo = ctx.get("check_beneficial_ownership", {})
    p = _profile(inp)
    high_risk_certified_owner = [
        o.name for o in p.beneficial_owners
        if o.ownership_pct >= BO_CERTIFICATION_PCT
        and o.jurisdiction_risk == HIGH_RISK_JURISDICTION_RISK
    ]
    jurisdictions = {o.jurisdiction for o in p.beneficial_owners}
    complex_ownership = len(p.beneficial_owners) > 2 and len(jurisdictions) > 1

    reasons = []
    if rating == "high":
        reasons.append("risk_rating_high")
    if hits:
        reasons.append("screening_hits")
    if bo.get("owners_in_20_25_band_high_risk"):
        reasons.append("beneficial_owner_in_unresolved_20_25_band")
    if high_risk_certified_owner:
        reasons.append("beneficial_owner_at_or_above_25pct_in_high_risk_jurisdiction")
    if complex_ownership:
        reasons.append("complex_multi_jurisdiction_ownership")
    required = bool(reasons)
    return _out({"edd_required": required, "reasons": reasons},
                [CLAUSES["cdd_edd"]], 0.9,
                notes="EDD required: " + (", ".join(reasons) if reasons else "no triggers"))


@register_atom("edd_review")
def edd_review(inp: AtomInput) -> AtomOutput:
    """EDD is a human review by design - the atom prepares the file, never clears it."""
    ctx = inp.context
    return _out({"edd_prepared": True,
                 "reasons": ctx.get("determine_edd_requirement", {}).get("reasons", [])},
                [CLAUSES["cdd_edd"]], 0.6, needs_human=True,
                notes="enhanced due diligence file prepared for specialist review")


@register_atom("final_onboarding_decision")
def final_onboarding_decision(inp: AtomInput) -> AtomOutput:
    ctx = inp.context
    verified = ctx.get("verify_identity_documents", {}).get("verified", False)
    edd = ctx.get("determine_edd_requirement", {}).get("edd_required", False)
    hits = ctx.get("screen_sanctions_pep", {}).get("screening_hits", [])
    if "sanctions_match" in hits:
        decision, conf = "rejected", 0.95
    elif edd:
        decision, conf = "edd_escalated", 0.85
    elif not verified:
        decision, conf = "rejected", 0.7
    else:
        decision, conf = "approved", 0.9
    return _out({"decision": decision},
                [CLAUSES["cdd_risk_profile"], CLAUSES["cip_documentary"]], conf,
                needs_human=(decision == "rejected"),
                notes=f"final decision: {decision}")


@register_atom("record_step_note")
def record_step_note(inp: AtomInput) -> AtomOutput:
    """Fallback for extracted steps with no mapped atom: keeps the step in the audit"""
    return _out({"recorded": True, "step_id": inp.step_id},
                [CLAUSES["cdd_risk_profile"]], 0.5, needs_human=True,
                notes="no atom implements this extracted step -> recorded for human handling")
