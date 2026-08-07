"""Neo4j process graph -> executable workflow spec (brief §7.1)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class CompileError(Exception):
    """Raised for conditions that would produce a broken runtime workflow."""


class NodeSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    kind: str
    atom: str | None = None
    step_id: str | None = None
    forced_hitl: bool = False
    hitl_reason: str | None = None
    evidence_required: list[str] = Field(default_factory=list)
    controls: list[str] = Field(default_factory=list)


class EdgeSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: str
    target: str
    condition: str | None = None


class WorkflowSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entry: str
    nodes: list[NodeSpec]
    edges: list[EdgeSpec]
    warnings: list[str] = Field(default_factory=list)

    def node(self, node_id: str) -> NodeSpec:
        return next(n for n in self.nodes if n.id == node_id)

    def successors(self, node_id: str) -> list[EdgeSpec]:
        return [e for e in self.edges if e.source == node_id]


ATOM_BY_STEP = {
    "collect customer information": "collect_customer_information",
    "verify identity documents": "verify_identity_documents",
    "callback verification": "callback_verification",
    "screen sanctions and pep lists": "screen_sanctions_pep",
    "screen sanctions": "screen_sanctions_pep",
    "assess jurisdiction risk": "assess_jurisdiction_risk",
    "check beneficial ownership": "check_beneficial_ownership",
    "compute risk rating": "compute_risk_rating",
    "determine edd requirement": "determine_edd_requirement",
    "edd review": "edd_review",
    "final onboarding decision": "final_onboarding_decision",
}

SUPPLIABLE_EVIDENCE = {
    "passport", "drivers_license", "national_id", "utility_bill", "bank_statement",
    "certificate_of_incorporation", "beneficial_ownership_certification",
    "director_passport", "proof_of_business_address", "expired_passport",
    "passport_renewal_receipt", "supplemental_address_document", "foreign_tax_id",
    "sanctions_screening_result", "adverse_media_result",
}


def _atom_for(step_name: str) -> str:
    return ATOM_BY_STEP.get(step_name.strip().lower(), "record_step_note")


def _detect_cycle(nodes: list[str], edges: list[tuple[str, str]]) -> list[str] | None:
    """DFS with colouring; returns the offending path for the error message."""
    adj: dict[str, list[str]] = {n: [] for n in nodes}
    for src, dst in edges:
        if src in adj and dst in adj:
            adj[src].append(dst)
    WHITE, GREY, BLACK = 0, 1, 2
    color = dict.fromkeys(nodes, WHITE)
    stack: list[str] = []

    def visit(n: str) -> list[str] | None:
        color[n] = GREY
        stack.append(n)
        for m in adj[n]:
            if color[m] == GREY:
                return stack[stack.index(m):] + [m]
            if color[m] == WHITE and (cycle := visit(m)) is not None:
                return cycle
        stack.pop()
        color[n] = BLACK
        return None

    for n in nodes:
        if color[n] == WHITE and (cycle := visit(n)) is not None:
            return cycle
    return None


def compile_workflow(process: dict) -> WorkflowSpec:
    """Compile a process description into a WorkflowSpec."""
    steps = process.get("steps", [])
    if not steps:
        raise CompileError("process graph has no steps - nothing to compile")
    deltas = process.get("deltas", [])
    by_id = {s["id"]: s for s in steps}

    for s in steps:
        unknown = [e for e in s.get("evidence_required", []) if e not in SUPPLIABLE_EVIDENCE]
        if unknown:
            raise CompileError(
                f"step {s['id']!r} requires evidence no atom can supply: {sorted(unknown)}. "
                "Add an atom that produces it, or fix the extracted evidence requirement."
            )

    raw_edges = [(s["id"], nx["target"]) for s in steps for nx in s.get("next", [])
                 if nx["target"] in by_id]
    if (cycle := _detect_cycle(list(by_id), raw_edges)) is not None:
        raise CompileError(
            "process graph contains a cycle: " + " -> ".join(cycle) +
            ". v1 forbids cycles (see compiler docstring): retries belong to the Temporal "
            "retry policy, not the process graph."
        )

    forced: dict[str, str] = {}
    for d in deltas:
        if d.get("severity") == "high":
            forced[d["about_element_id"]] = (
                f"unresolved high-severity delta {d['id']}: {d.get('description', '')[:160]}"
            )

    nodes: list[NodeSpec] = []
    edges: list[EdgeSpec] = []
    warnings: list[str] = []

    ordered = sorted(steps, key=lambda s: (s.get("sequence_hint") is None,
                                           s.get("sequence_hint", 0), s["id"]))
    for s in ordered:
        atom_node = NodeSpec(
            id=s["id"], kind="atom", atom=_atom_for(s["name"]), step_id=s["id"],
            evidence_required=s.get("evidence_required", []),
            controls=s.get("controls", []),
        )
        nodes.append(atom_node)
        tail = s["id"]

        if s.get("controls"):
            guard_id = f"{s['id']}::guard"
            nodes.append(NodeSpec(id=guard_id, kind="guard", step_id=s["id"],
                                  controls=s["controls"]))
            edges.append(EdgeSpec(source=tail, target=guard_id))
            tail = guard_id

        if s["id"] in forced:
            hitl_id = f"{s['id']}::hitl"
            nodes.append(NodeSpec(id=hitl_id, kind="hitl", step_id=s["id"],
                                  forced_hitl=True, hitl_reason=forced[s["id"]]))
            edges.append(EdgeSpec(source=tail, target=hitl_id))
            tail = hitl_id

        for nx in s.get("next", []):
            if nx["target"] not in by_id:
                warnings.append(f"step {s['id']}: NEXT points at unknown node {nx['target']!r}")
                continue
            edges.append(EdgeSpec(source=tail, target=nx["target"],
                                  condition=nx.get("condition")))

    entry = ordered[0]["id"]
    reachable, frontier = {entry}, [entry]
    while frontier:
        cur = frontier.pop()
        for e in edges:
            if e.source == cur and e.target not in reachable:
                reachable.add(e.target)
                frontier.append(e.target)
    for n in nodes:
        if n.id not in reachable:
            warnings.append(f"unreachable node {n.id!r} - no path from entry {entry!r}")

    return WorkflowSpec(entry=entry, nodes=nodes, edges=edges, warnings=warnings)


def to_langgraph(spec: WorkflowSpec, executor):
    """Materialize the spec as a LangGraph StateGraph."""
    from langgraph.graph import END, StateGraph

    builder = StateGraph(dict)
    for n in spec.nodes:
        builder.add_node(n.id, lambda state, _n=n: executor(_n, state))
    builder.set_entry_point(spec.entry)

    for n in spec.nodes:
        outs = spec.successors(n.id)
        if not outs:
            builder.add_edge(n.id, END)
        elif len(outs) == 1 and outs[0].condition is None:
            builder.add_edge(n.id, outs[0].target)
        else:
            mapping = {(e.condition or "default"): e.target for e in outs}

            def route(state, _mapping=mapping):
                branch = state.get("branch") or "default"
                return _mapping.get(branch, next(iter(_mapping.values())))

            builder.add_conditional_edges(n.id, route, mapping)
    return builder.compile()
