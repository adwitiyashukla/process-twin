"""The main graph queries, retriever expansion, and explorer JSON."""

from __future__ import annotations

ALL_DELTAS = """
MATCH (d:Delta)-[:ABOUT]->(el)
OPTIONAL MATCH (d)-[:WRITTEN_VIEW]->(c:Clause)
OPTIONAL MATCH (d)-[:PRACTICED_VIEW]->(p)
RETURN d.id AS id, d.kind AS kind, d.severity AS severity, d.description AS description,
       d.recommendation AS recommendation, d.support_count AS support_count,
       labels(el)[0] AS about_label, el.name AS about_name,
       collect(DISTINCT c.clause_id) AS written_evidence,
       collect(DISTINCT coalesce(p.id, '')) AS practiced_evidence
ORDER BY CASE d.severity WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END, d.id
"""

STEP_PROVENANCE = """
MATCH (s:Step {name: $step_name})-[df:DERIVED_FROM]->(src)
RETURN s.name AS step, s.confidence AS confidence, df.source_type AS source_type,
       df.weight AS weight, labels(src)[0] AS source_kind,
       coalesce(src.clause_id, src.id) AS source_ref
ORDER BY df.weight DESC, source_ref
"""

PROVENANCE_COVERAGE = """
MATCH (n) WHERE any(l IN labels(n) WHERE l IN
      ['Step','Control','Exception','Evidence','EscalationPath'])
OPTIONAL MATCH (n)-[df:DERIVED_FROM]->()
WITH n, count(df) AS prov
RETURN count(n) AS elements, sum(CASE WHEN prov = 0 THEN 1 ELSE 0 END) AS orphans
"""

STEP_CLAUSE_IDS = """
MATCH (s:Step {id: $step_id})-[:DERIVED_FROM]->(c:Clause)
WITH collect(c.clause_id) AS direct
OPTIONAL MATCH (s2:Step {id: $step_id})-[:NEXT|GOVERNED_BY*1..1]-(nb)-[:DERIVED_FROM]->(c2:Clause)
RETURN direct + collect(DISTINCT c2.clause_id) AS clause_ids
"""

GRAPH_JSON = """
MATCH (n) WHERE any(l IN labels(n) WHERE l IN
      ['Process','Step','Control','Exception','Evidence','EscalationPath','Delta'])
OPTIONAL MATCH (n)-[r:HAS_STEP|NEXT|REQUIRES|GOVERNED_BY|ON_EXCEPTION|ESCALATES_TO|ABOUT]->(m)
RETURN n.id AS id, labels(n)[0] AS label, coalesce(n.name, n.description) AS name,
       n.severity AS severity, n.support_count AS support,
       collect({type: type(r), target: m.id}) AS edges
"""


def step_clause_ids(session, step_id: str) -> list[str]:
    """Graph expansion for the retriever: clauses already linked to this step."""
    record = session.run(STEP_CLAUSE_IDS, {"step_id": step_id}).single()
    return [c for c in (record["clause_ids"] if record else []) if c]
