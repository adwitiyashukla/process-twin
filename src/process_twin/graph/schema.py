"""Neo4j constraints + indexes (brief §5). Uniqueness on every id is what makes the
loader's MERGE semantics idempotent — re-seeding updates in place, never duplicates."""

from __future__ import annotations

CONSTRAINTS = [
    "CREATE CONSTRAINT process_id IF NOT EXISTS FOR (n:Process) REQUIRE n.id IS UNIQUE",
    "CREATE CONSTRAINT step_id IF NOT EXISTS FOR (n:Step) REQUIRE n.id IS UNIQUE",
    "CREATE CONSTRAINT control_id IF NOT EXISTS FOR (n:Control) REQUIRE n.id IS UNIQUE",
    "CREATE CONSTRAINT exception_id IF NOT EXISTS FOR (n:Exception) REQUIRE n.id IS UNIQUE",
    "CREATE CONSTRAINT evidence_id IF NOT EXISTS FOR (n:Evidence) REQUIRE n.id IS UNIQUE",
    "CREATE CONSTRAINT escalation_id IF NOT EXISTS FOR (n:EscalationPath) REQUIRE n.id IS UNIQUE",
    "CREATE CONSTRAINT delta_id IF NOT EXISTS FOR (n:Delta) REQUIRE n.id IS UNIQUE",
    "CREATE CONSTRAINT clause_id IF NOT EXISTS FOR (n:Clause) REQUIRE n.clause_id IS UNIQUE",
    "CREATE CONSTRAINT segment_id IF NOT EXISTS FOR (n:InterviewSegment) REQUIRE n.id IS UNIQUE",
    "CREATE CONSTRAINT pattern_id IF NOT EXISTS FOR (n:CaseLogPattern) REQUIRE n.id IS UNIQUE",
    "CREATE INDEX step_name IF NOT EXISTS FOR (n:Step) ON (n.name)",
]

LABEL_BY_TYPE = {
    "step": "Step",
    "control": "Control",
    "exception": "Exception",
    "evidence_requirement": "Evidence",
    "escalation": "EscalationPath",
}


def ensure_schema(session) -> None:
    for stmt in CONSTRAINTS:
        session.run(stmt)
