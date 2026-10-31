"""HTTP API + static UI.

    uvicorn atlas.api:app --app-dir engine --port 8787
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .builders import build_all
from .cli import DEFAULT_DB
from .ontology import Basis, BuyingRole, EdgeType, NodeType
from .problems import PROBLEMS
from .report import buying_committee, entry_paths, org_tree, ranked_people, signals
from .store import Store, slug
from .targets import TARGET as T

WEB = Path(__file__).resolve().parents[2] / "web"
app = FastAPI(title="Enterprise Atlas")
PROBLEM = PROBLEMS[os.environ.get("ATLAS_PROBLEM", "warranty-aftersales-analytics")]


def store() -> Store:
    return Store(os.environ.get("ATLAS_DB", DEFAULT_DB))


def _edge(e) -> dict:
    return {"id": e.id, "source": e.src, "target": e.dst, "type": e.type, "layer": e.layer,
            "confidence": e.confidence, "status": e.status, "n": len(e.assertions),
            "bases": sorted({a["basis"] for a in e.assertions}),
            "observed_at": max(a["observed_at"] for a in e.assertions)}


@app.get("/api/meta")
def meta():
    s = store()
    return {"company": T.COMPANY_NAME, "company_id": T.COMPANY_ID, "problem": {"id": PROBLEM.id, "label": PROBLEM.label,
            "description": PROBLEM.description}, "stats": s.stats(),
            "node_types": [n.value for n in NodeType], "edge_types": [e.value for e in EdgeType],
            "bases": [b.value for b in Basis], "roles": [r.value for r in BuyingRole]}


@app.get("/api/graph")
def graph(min_confidence: float = 0.0, layers: Optional[str] = None, include_people: bool = True):
    s = store()
    wanted = set(layers.split(",")) if layers else None
    edges = [e for e in s.edges() if e.confidence >= min_confidence and (not wanted or e.layer in wanted)]
    ents = {e["id"]: e for e in s.entities()}
    used = {x for e in edges for x in (e.src, e.dst)}
    nodes = []
    for eid in used:
        ent = ents.get(eid)
        if not ent or (not include_people and ent["type"] == "Person"):
            continue
        p = ent["props"]
        nodes.append({"id": eid, "type": ent["type"], "label": ent["label"],
                      "score": (p.get("scores") or {}).get("score"), "roles": [r["role"] for r in p.get("buying_roles") or []],
                      "name_visible": p.get("name_visible")})
    ids = {n["id"] for n in nodes}
    return {"nodes": nodes, "edges": [_edge(e) for e in edges if e.src in ids and e.dst in ids]}


@app.get("/api/org")
def org():
    return org_tree(store(), T.COMPANY_ID)


@app.get("/api/committee")
def committee(limit: int = 12):
    return buying_committee(store(), PROBLEM, limit)


@app.get("/api/paths")
def paths():
    return entry_paths(store(), PROBLEM)


@app.get("/api/signals")
def get_signals():
    return signals(store())


@app.get("/api/people")
def people(limit: int = 200):
    return ranked_people(store(), limit)


@app.get("/api/entities")
def entities(q: str = "", type: Optional[str] = None, limit: int = 30):
    s = store()
    out = []
    ql = q.lower()
    for e in s.entities(NodeType(type) if type else None):
        if not ql or ql in e["label"].lower() or ql in (e["props"].get("headline") or "").lower():
            out.append({"id": e["id"], "type": e["type"], "label": e["label"]})
        if len(out) >= limit:
            break
    return out


@app.get("/api/entity/{eid:path}")
def entity(eid: str):
    s = store()
    ent = s.entity(eid)
    if not ent:
        raise HTTPException(404)
    edges = s.neighbors(eid)
    ev_ids = {a["evidence_id"] for e in edges for a in e.assertions if a["evidence_id"]}
    evidence = {e["id"]: e for e in s.evidence(ev_ids)}
    labels = {x["id"]: x["label"] for x in s.entities()}
    rels = []
    for e in sorted(edges, key=lambda e: -e.confidence):
        rels.append({**_edge(e), "source_label": labels.get(e.src, e.src), "target_label": labels.get(e.dst, e.dst),
                     "assertions": [{"id": a["id"], "basis": a["basis"], "confidence": a["confidence"], "status": a["status"],
                                     "observed_at": a["observed_at"], "extractor": a["extractor"], "rationale": a["rationale"],
                                     "props": a["props"], "evidence": evidence.get(a["evidence_id"])} for a in e.assertions]})
    return {"entity": ent, "relationships": rels}


@app.get("/api/evidence")
def evidence(basis: Optional[str] = None, limit: int = 500):
    s = store()
    rows = s.evidence()
    counts = {r[0]: r[1] for r in s.db.execute("SELECT evidence_id, COUNT(*) FROM assertions GROUP BY evidence_id")}
    rows = [dict(r, claims=counts.get(r["id"], 0)) for r in rows if not basis or r["basis"] == basis]
    rows.sort(key=lambda r: (r["basis"], r["title"]))
    return rows[:limit]


# ------------------------------------------------------------- curation
class NewEntity(BaseModel):
    type: str
    label: str
    description: Optional[str] = None


class NewAssertion(BaseModel):
    src: str
    dst: str
    type: str
    basis: str = "analyst"
    confidence: float = 0.7
    url: Optional[str] = None
    note: str = ""


class Merge(BaseModel):
    src: str
    dst: str


class Reject(BaseModel):
    reason: str = ""


@app.post("/api/entities")
def create_entity(body: NewEntity):
    s = store()
    t = NodeType(body.type)
    eid = f"{t.value.lower()}:{slug(body.label)}"
    s.upsert_entity(eid, t, body.label, {"description": body.description, "source": "analyst"})
    s.commit()
    return {"id": eid}


@app.post("/api/assertions")
def create_assertion(body: NewAssertion):
    s = store()
    if not s.entity(body.src) or not s.entity(body.dst):
        raise HTTPException(400, "unknown entity")
    basis = Basis(body.basis)
    ev = None
    if body.url:
        ev = s.put_evidence(url=body.url, title=body.note or body.url, basis=basis, provider="analyst", excerpt=body.note)
    elif basis not in (Basis.ANALYST,):
        raise HTTPException(400, "a source URL is required for non-analyst claims")
    aid = s.assert_edge(body.src, body.dst, EdgeType(body.type), basis=basis, confidence=body.confidence,
                        evidence_id=ev, extractor="analyst", rationale=body.note)
    s.commit()
    return {"id": aid}


@app.post("/api/merge")
def merge(body: Merge):
    s = store()
    try:
        s.merge_entities(body.src, body.dst)
    except KeyError:
        raise HTTPException(404)
    s.commit()
    return {"ok": True}


@app.post("/api/assertions/{aid:path}/reject")
def reject(aid: str, body: Reject):
    s = store()
    try:
        s.reject_assertion(aid, body.reason)
    except KeyError:
        raise HTTPException(404)
    s.commit()
    return {"ok": True}


@app.post("/api/rebuild")
def rebuild():
    s = store()
    return build_all(s, PROBLEM)


class Urls(BaseModel):
    urls: list[str]


@app.post("/api/ingest/urls")
def ingest_urls(body: Urls):
    from .collectors.web import harvest_urls
    s = store()
    out = harvest_urls(s, body.urls)
    out["build"] = build_all(s, PROBLEM)["web"]
    return out


@app.post("/api/harvest/needle")
def harvest_needle(pages: int = 2):
    from .collectors.needle import NeedleClient, harvest_people, plan_people_queries
    try:
        client = NeedleClient()
    except RuntimeError as e:
        raise HTTPException(400, str(e))
    s = store()
    out = harvest_people(s, client, plan_people_queries(PROBLEM, list(T.LINKEDIN_COMPANIES.values()), pages))
    out["build"] = build_all(s, PROBLEM)["needle_people"]
    return out


@app.get("/api/sources")
def sources():
    s = store()
    raw = {r[0]: {"documents": r[1], "last": r[2]} for r in
           s.db.execute("SELECT collector, COUNT(*), MAX(fetched_at) FROM raw_documents GROUP BY collector")}
    return {
        "collected": raw,
        "configured": {
            "needle": bool(os.environ.get("NEEDLE_API_KEY")),
            "anthropic": bool(os.environ.get("ANTHROPIC_API_KEY")),
        },
    }


if WEB.exists():
    app.mount("/assets", StaticFiles(directory=WEB), name="assets")

    @app.get("/")
    def index():
        return FileResponse(WEB / "index.html")
