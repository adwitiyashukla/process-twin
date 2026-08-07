# The graph schema

This is the shape of the process twin in Neo4j. I wrote it before building the loader so
that extraction had a fixed target to aim at.

The main idea: conflicting sources never get averaged into one value. A conflict becomes a
Delta node that you can query, visualise, and put in front of a person. Everything else in
the schema exists to make that node meaningful, which mostly means tracking where every
piece of information came from.

## Nodes

```
(:Process        {id, name, version, domain: "kyc-onboarding"})
(:Step           {id, name, description, step_type: "task"|"decision"|"control_check",
                  actor: "human"|"agent"|"system", confidence: float, status: "canonical"})
(:Control        {id, name, control_type: "verification"|"approval"|"screening"|"recordkeeping",
                  mandatory: bool, confidence: float})
(:Exception      {id, trigger_description, handling, frequency_estimate, confidence: float})
(:Evidence       {id, artifact_type})
(:EscalationPath {id, to_role, sla_hours})
(:Delta          {id, kind, description, severity, recommendation})

(:Clause           {clause_id, source_doc, section_path, text_hash})
(:InterviewSegment {id, persona, transcript_ref, quote_span})
(:CaseLogPattern   {id, pattern_description, support_count})
```

The last three are provenance nodes. A Clause is a piece of written policy, an
InterviewSegment is something a practitioner said, and a CaseLogPattern is behaviour I
mined out of the historical cases.

Delta kinds are a fixed set: threshold, gap, unwritten_rule, sequence, stricter_practice,
skipped_step, practitioner_conflict.

## Relationships

```
(:Process)-[:HAS_STEP]->(:Step)
(:Step)-[:NEXT {condition}]->(:Step)
(:Step)-[:REQUIRES]->(:Evidence)
(:Step)-[:GOVERNED_BY]->(:Control)
(:Step)-[:ON_EXCEPTION]->(:Exception)
(:Exception)-[:ESCALATES_TO]->(:EscalationPath)

(:Step|:Control|:Exception)-[:DERIVED_FROM {source_type, weight}]->(:Clause|:InterviewSegment|:CaseLogPattern)

(:Delta)-[:ABOUT]->(:Step|:Control|:Exception)
(:Delta)-[:WRITTEN_VIEW]->(:Clause)
(:Delta)-[:PRACTICED_VIEW]->(:InterviewSegment|:CaseLogPattern)
```

Every extracted element carries at least one DERIVED_FROM edge. This is not optional. The
loader refuses to create a node without provenance, and there is an acceptance query that
counts orphans and expects zero. If something is in the graph, you can trace where it came
from.

The three Delta edges are what make the diff demo work. One node points at the thing it is
about, at the written source on one side, and at the practised evidence on the other.

## Rules

Uniqueness constraints on every id and clause_id, plus an index on Step.name.

`confidence` on a node is how sure extraction was. `weight` on a DERIVED_FROM edge is how
strongly that particular source backs the element. Sources agreeing raises confidence.
Sources disagreeing does not average anything, it creates a Delta.

## The two queries that matter

Everything else in the schema exists so these two work.

Every divergence with both sides of its evidence:

```cypher
MATCH (d:Delta)-[:ABOUT]->(el)
OPTIONAL MATCH (d)-[:WRITTEN_VIEW]->(c:Clause)
OPTIONAL MATCH (d)-[:PRACTICED_VIEW]->(p)
RETURN d.id, d.kind, d.severity, labels(el)[0] AS about, el.name,
       collect(DISTINCT c.clause_id) AS written_evidence,
       collect(DISTINCT coalesce(p.persona, p.pattern_description)) AS practiced_evidence
ORDER BY d.severity DESC, d.id
```

Where everything about one step came from:

```cypher
MATCH (s:Step {name: $step_name})-[df:DERIVED_FROM]->(src)
RETURN s.name, s.confidence, df.source_type, df.weight,
       labels(src)[0] AS source_kind,
       coalesce(src.clause_id, src.id) AS source_ref
ORDER BY df.weight DESC
```

The second one is why I used a graph. In a flat vector store you can ask what is similar to
something. You cannot ask where a piece of knowledge came from, and for this project that is
the question that matters.
