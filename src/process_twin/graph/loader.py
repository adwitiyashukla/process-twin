"""Write the reconciled process + deltas into Neo4j with FULL provenance (brief §5)."""

from __future__ import annotations

from process_twin.graph.schema import LABEL_BY_TYPE, ensure_schema
from process_twin.ingestion.case_logs import CaseLogPattern
from process_twin.ingestion.transcripts import TranscriptSegment
from process_twin.schemas.process import CanonicalElement, Delta

PROCESS_ID = "kyc-onboarding-v1"


def load_graph(
    session,
    canonicals: list[CanonicalElement],
    deltas: list[Delta],
    segments: list[TranscriptSegment],
    patterns: list[CaseLogPattern],
    clause_meta: list[dict] | None = None,
) -> dict:
    ensure_schema(session)
    session.run(
        "MERGE (p:Process {id: $id}) SET p.name = $name, p.version = 1, "
        "p.domain = 'kyc-onboarding'",
        {"id": PROCESS_ID, "name": "KYC/CDD customer onboarding"},
    )

    for c in clause_meta or []:
        session.run(
            "MERGE (c:Clause {clause_id: $clause_id}) "
            "SET c.source_doc = $source_doc, c.section_path = $section_path, "
            "c.text_hash = $checksum",
            c,
        )
    for s in segments:
        session.run(
            "MERGE (s:InterviewSegment {id: $id}) SET s.persona = $persona, "
            "s.transcript_ref = $ref, s.quote_span = $quote",
            {"id": s.id, "persona": s.persona_name, "ref": f"{s.persona_id} transcript",
             "quote": s.quote_span},
        )
    for p in patterns:
        session.run(
            "MERGE (p:CaseLogPattern {id: $id}) SET p.pattern_description = $desc, "
            "p.support_count = $n, p.case_ids = $cases",
            {"id": p.id, "desc": p.pattern_description, "n": p.support_count,
             "cases": p.case_ids},
        )

    provenance_edges = 0
    for el in canonicals:
        if not el.provenance:
            raise ValueError(f"{el.id}: element without provenance cannot enter the graph")
        label = LABEL_BY_TYPE[el.element_type]
        session.run(
            f"MERGE (n:{label} {{id: $id}}) SET n.name = $name, n.description = $desc, "
            "n.actor = $actor, n.confidence = $conf, n.status = 'canonical', "
            "n.attributes_json = $attrs, n.sequence_hint = $seq",
            {"id": el.id, "name": el.name, "desc": el.description, "actor": el.actor,
             "conf": el.confidence, "attrs": str(sorted(el.attributes.items())),
             "seq": el.sequence_hint},
        )
        if el.element_type == "step":
            session.run(
                "MATCH (p:Process {id: $pid}), (s:Step {id: $sid}) MERGE (p)-[:HAS_STEP]->(s)",
                {"pid": PROCESS_ID, "sid": el.id},
            )
        for sp in el.provenance:
            target = {"policy": ("Clause", "clause_id"), "interview": ("InterviewSegment", "id"),
                      "case_log": ("CaseLogPattern", "id")}[sp.source_type]
            tlabel, tkey = target
            session.run(
                f"MATCH (n:{label} {{id: $id}}) "
                f"MERGE (t:{tlabel} {{{tkey}: $ref}}) "
                "MERGE (n)-[d:DERIVED_FROM]->(t) SET d.source_type = $st, d.weight = 1.0",
                {"id": el.id, "ref": sp.ref, "st": sp.source_type},
            )
            provenance_edges += 1

    steps = sorted(
        (e for e in canonicals if e.element_type == "step" and e.sequence_hint is not None),
        key=lambda e: e.sequence_hint,
    )
    for a, b in zip(steps, steps[1:], strict=False):
        session.run(
            "MATCH (a:Step {id: $a}), (b:Step {id: $b}) MERGE (a)-[:NEXT]->(b)",
            {"a": a.id, "b": b.id},
        )

    for d in deltas:
        session.run(
            "MERGE (d:Delta {id: $id}) SET d.kind = $kind, d.severity = $sev, "
            "d.description = $desc, d.recommendation = $rec, d.support_count = $n",
            {"id": d.id, "kind": d.kind, "sev": d.severity, "desc": d.description,
             "rec": d.recommendation, "n": d.support_count},
        )
        session.run(
            "MATCH (d:Delta {id: $id}) MATCH (el {id: $about}) MERGE (d)-[:ABOUT]->(el)",
            {"id": d.id, "about": d.about_element_id},
        )
        for ref in d.written_view:
            session.run(
                "MATCH (d:Delta {id: $id}) MERGE (c:Clause {clause_id: $ref}) "
                "MERGE (d)-[:WRITTEN_VIEW]->(c)",
                {"id": d.id, "ref": ref},
            )
        for ref in d.practiced_view:
            label = "CaseLogPattern" if ref.startswith("PAT-") else "InterviewSegment"
            session.run(
                f"MATCH (d:Delta {{id: $id}}) MERGE (t:{label} {{id: $ref}}) "
                "MERGE (d)-[:PRACTICED_VIEW]->(t)",
                {"id": d.id, "ref": ref},
            )

    return {"elements": len(canonicals), "deltas": len(deltas),
            "provenance_edges": provenance_edges, "next_edges": max(0, len(steps) - 1)}
