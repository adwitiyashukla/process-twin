# Neo4j graph schema — the process twin (brief §5)

Specification written ahead of the phase-3 loader so extraction targets a fixed contract.
The one-sentence thesis: **conflicting sources are never averaged away — a conflict becomes
a `Delta` node**, first-class, queryable, and visualized. Everything else exists to make
that queryable with full provenance.

## Nodes

```
(:Process        {id, name, version, domain: "kyc-onboarding"})
(:Step           {id, name, description, step_type: "task"|"decision"|"control_check",
                  actor: "human"|"agent"|"system", confidence: float, status: "canonical"})
(:Control        {id, name, control_type: "verification"|"approval"|"screening"|"recordkeeping",
                  mandatory: bool, confidence: float})
(:Exception      {id, trigger_description, handling, frequency_estimate, confidence: float})
(:Evidence       {id, artifact_type})              // "passport", "utility_bill", …
(:EscalationPath {id, to_role, sla_hours})
(:Delta          {id, kind: "threshold"|"gap"|"unwritten_rule"|"sequence"|"stricter_practice"|
                        "skipped_step"|"practitioner_conflict",
                  description, severity: "low"|"medium"|"high", recommendation})
(:Clause           {clause_id, source_doc, section_path, text_hash})   // provenance: written
(:InterviewSegment {id, persona, transcript_ref, quote_span})          // provenance: tacit
(:CaseLogPattern   {id, pattern_description, support_count})           // provenance: observed
```

## Relationships

```
(:Process)-[:HAS_STEP]->(:Step)
(:Step)-[:NEXT {condition: str|null}]->(:Step)
(:Step)-[:REQUIRES]->(:Evidence)
(:Step)-[:GOVERNED_BY]->(:Control)
(:Step)-[:ON_EXCEPTION]->(:Exception)
(:Exception)-[:ESCALATES_TO]->(:EscalationPath)

// provenance — EVERY extracted element carries at least one:
(:Step|:Control|:Exception)-[:DERIVED_FROM {source_type, weight}]->(:Clause|:InterviewSegment|:CaseLogPattern)

// the diff structure:
(:Delta)-[:ABOUT]->(:Step|:Control|:Exception)
(:Delta)-[:WRITTEN_VIEW]->(:Clause)
(:Delta)-[:PRACTICED_VIEW]->(:InterviewSegment|:CaseLogPattern)
```

## Rules

* Uniqueness constraints on every `id` / `clause_id`; index on `Step.name`.
* `confidence` = extraction confidence (0–1), set by reconciliation; `DERIVED_FROM.weight`
  = how strongly that source supports the element.
* Where sources disagree on an attribute, the **written** value stays canonical and the
  disagreement becomes a `Delta` (brief §6.2) — the machine never silently picks a side.

## The two killer queries (phase-3 acceptance)

Every delta with both evidence sides:

```cypher
MATCH (d:Delta)-[:ABOUT]->(el)
OPTIONAL MATCH (d)-[:WRITTEN_VIEW]->(c:Clause)
OPTIONAL MATCH (d)-[:PRACTICED_VIEW]->(p)
RETURN d.id, d.kind, d.severity, labels(el)[0] AS about, el.name,
       collect(DISTINCT c.clause_id) AS written_evidence,
       collect(DISTINCT coalesce(p.persona, p.pattern_description)) AS practiced_evidence
ORDER BY d.severity DESC, d.id
```

Full provenance chain for one step:

```cypher
MATCH (s:Step {name: $step_name})-[df:DERIVED_FROM]->(src)
RETURN s.name, s.confidence, type(df) AS rel, df.source_type, df.weight,
       labels(src)[0] AS source_kind,
       coalesce(src.clause_id, src.id) AS source_ref
ORDER BY df.weight DESC
```
