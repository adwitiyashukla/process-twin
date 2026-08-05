"""Graph loader mechanics against a recording fake session — proves the Cypher shape
(constraints, provenance edge per span, delta wiring) without a Neo4j server. The live
acceptance query (PROVENANCE_COVERAGE: zero orphans) runs in seed_graph on real infra."""

from process_twin.extraction.delta_detect import detect_deltas
from process_twin.graph.loader import load_graph
from process_twin.graph.queries import PROVENANCE_COVERAGE  # noqa: F401 (documented here)
from process_twin.graph.schema import CONSTRAINTS
from process_twin.ingestion.case_logs import CaseLogPattern
from process_twin.ingestion.transcripts import TranscriptSegment
from process_twin.schemas.process import AttributeConflict, CanonicalElement, SourceSpan


class FakeSession:
    def __init__(self):
        self.calls: list[tuple[str, dict]] = []

    def run(self, query, params=None):
        self.calls.append((" ".join(query.split()), params or {}))
        return self

    def single(self):
        return None


def _canon(id_, etype, name, spans, seq=None):
    return CanonicalElement(
        id=id_, element_type=etype, name=name, description=f"{name} description",
        confidence=0.9, provenance=spans, sequence_hint=seq,
    )


def _inputs():
    canonicals = [
        _canon("EL-verify", "step", "verify identity documents",
               [SourceSpan(source_type="policy", ref="FFIEC-CIP-¶2"),
                SourceSpan(source_type="interview", ref="P1-S1")], seq=2),
        _canon("EL-screen", "step", "screen sanctions",
               [SourceSpan(source_type="policy", ref="FFIEC-CDD-¶4")], seq=3),
        _canon("EL-callback", "control", "callback verification",
               [SourceSpan(source_type="policy", ref="FFIEC-CIP-¶7"),
                SourceSpan(source_type="case_log", ref="PAT-CALLBACK-SKIPPED-SMALL")]),
    ]
    patterns = [CaseLogPattern(id="PAT-CALLBACK-SKIPPED-SMALL", pattern_description="d",
                               support_count=6, case_ids=["HC-039"])]
    segments = [TranscriptSegment(id="P1-S1", persona_id="P1", persona_name="Priya Raghavan",
                                  question="q", text="t" * 120, quote_span="t")]
    conflicts = [AttributeConflict(
        element_id="EL-callback", element_name="callback verification",
        attribute="callback_min_activity_usd", written_value=None, practiced_value="10000",
        written_spans=[SourceSpan(source_type="policy", ref="FFIEC-CIP-¶7")],
        practiced_spans=[SourceSpan(source_type="interview", ref="P4-S4")],
    )]
    deltas = detect_deltas(canonicals, conflicts, patterns)
    assert deltas, "fixture must produce at least one delta to exercise the wiring"
    return canonicals, deltas, segments, patterns


def test_constraints_run_before_any_merge():
    session = FakeSession()
    load_graph(session, *_inputs())
    first_queries = [q for q, _ in session.calls[: len(CONSTRAINTS)]]
    assert all("CONSTRAINT" in q or "INDEX" in q for q in first_queries)


def test_every_element_gets_node_and_all_provenance_edges():
    session = FakeSession()
    stats = load_graph(session, *_inputs())
    assert stats["elements"] == 3
    assert stats["provenance_edges"] == 5  # 2 + 1 + 2 spans
    derived = [q for q, _ in session.calls if "DERIVED_FROM" in q]
    assert len(derived) == 5
    # provenance targets typed correctly by source
    assert any("Clause" in q and p.get("ref") == "FFIEC-CIP-¶2"
               for q, p in session.calls if "DERIVED_FROM" in q)
    assert any("CaseLogPattern" in q and p.get("ref") == "PAT-CALLBACK-SKIPPED-SMALL"
               for q, p in session.calls if "DERIVED_FROM" in q)


def test_next_chain_follows_written_sequence():
    session = FakeSession()
    stats = load_graph(session, *_inputs())
    assert stats["next_edges"] == 1  # EL-verify(2) -> EL-screen(3)
    next_calls = [p for q, p in session.calls if "MERGE (a)-[:NEXT]->(b)" in q]
    assert next_calls == [{"a": "EL-verify", "b": "EL-screen"}]


def test_deltas_wired_with_about_and_practiced_view():
    session = FakeSession()
    load_graph(session, *_inputs())
    assert any("MERGE (d:Delta" in q for q, _ in session.calls)
    assert any("ABOUT" in q for q, _ in session.calls)
    pv = [p for q, p in session.calls if "PRACTICED_VIEW" in q]
    assert any(p.get("ref", "").startswith("PAT-") for p in pv)
