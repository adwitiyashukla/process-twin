"""Explorer backend (brief §11): graph + delta JSON for the browser view.

Serves from live Neo4j when reachable, else falls back to data/derived/ dumps — so the
explorer works right after `seed_graph --skip-graph` too. Deviation note: the page uses
vis-network fed by these endpoints instead of neovis-over-bolt, so no database
credentials ever reach the browser (docs/architecture.md, phase 3).
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from process_twin.config import get_settings
from process_twin.graph.queries import ALL_DELTAS, GRAPH_JSON

router = APIRouter()
DERIVED = Path("data/derived")


def _neo4j_session():
    try:
        from neo4j import GraphDatabase

        s = get_settings()
        driver = GraphDatabase.driver(
            s.neo4j_uri, auth=(s.neo4j_user, s.neo4j_password),
            connection_timeout=2.0,
        )
        driver.verify_connectivity()
        return driver
    except Exception:  # noqa: BLE001 — any failure means: use the derived-file fallback
        return None


@router.get("/api/deltas")
def deltas() -> list[dict]:
    driver = _neo4j_session()
    if driver is not None:
        with driver.session() as session:
            rows = [dict(r) for r in session.run(ALL_DELTAS)]
        driver.close()
        return rows
    if (DERIVED / "deltas.json").exists():
        ds = json.loads((DERIVED / "deltas.json").read_text(encoding="utf-8"))
        return [{
            "id": d["id"], "kind": d["kind"], "severity": d["severity"],
            "description": d["description"], "recommendation": d["recommendation"],
            "support_count": d["support_count"], "about_name": d["about_element_id"],
            "written_evidence": d["written_view"], "practiced_evidence": d["practiced_view"],
        } for d in ds]
    return []


@router.get("/api/graph")
def graph() -> dict:
    driver = _neo4j_session()
    nodes, edges = [], []
    if driver is not None:
        with driver.session() as session:
            for r in session.run(GRAPH_JSON):
                nodes.append({"id": r["id"], "label": r["label"], "name": r["name"],
                              "severity": r["severity"], "support": r["support"]})
                edges.extend(
                    {"from": r["id"], "to": e["target"], "type": e["type"]}
                    for e in r["edges"] if e["target"]
                )
        driver.close()
        return {"nodes": nodes, "edges": edges, "source": "neo4j"}
    if (DERIVED / "canonicals.json").exists():
        canonicals = json.loads((DERIVED / "canonicals.json").read_text(encoding="utf-8"))
        ds = json.loads((DERIVED / "deltas.json").read_text(encoding="utf-8"))
        label_by_type = {"step": "Step", "control": "Control", "exception": "Exception",
                         "evidence_requirement": "Evidence", "escalation": "EscalationPath"}
        for c in canonicals:
            nodes.append({"id": c["id"], "label": label_by_type[c["element_type"]],
                          "name": c["name"], "severity": None, "support": None})
        steps = sorted((c for c in canonicals
                        if c["element_type"] == "step" and c["sequence_hint"] is not None),
                       key=lambda c: c["sequence_hint"])
        edges.extend({"from": a["id"], "to": b["id"], "type": "NEXT"}
                     for a, b in zip(steps, steps[1:], strict=False))
        for d in ds:
            nodes.append({"id": d["id"], "label": "Delta", "name": d["description"][:80],
                          "severity": d["severity"], "support": d["support_count"]})
            edges.append({"from": d["id"], "to": d["about_element_id"], "type": "ABOUT"})
        return {"nodes": nodes, "edges": edges, "source": "derived-files"}
    return {"nodes": [], "edges": [], "source": "empty"}


@router.get("/explorer", response_class=HTMLResponse)
def explorer_page() -> str:
    return Path("explorer/index.html").read_text(encoding="utf-8")
