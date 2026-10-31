"""Read models over the store: org tree, buying committee, entry paths, graph export."""
from __future__ import annotations

from collections import defaultdict

from .ontology import BuyingRole, NodeType
from .problems import Problem
from .store import Store

ROLE_ORDER = [r.value for r in BuyingRole]


def org_tree(store: Store, root: str) -> dict:
    """Company -> units -> functions -> teams -> people, from BELONGS_TO / WORKS_IN edges."""
    # Each node hangs under its single best parent (highest confidence, then most recent observation),
    # so a unit that moved (e.g. Mobility merged into Mercedes-Benz AG in 2025) appears once.
    best: dict[str, tuple] = {}
    for e in store.edges("type IN ('BELONGS_TO','WORKS_IN')"):
        if store.entity(e.dst) and store.entity(e.dst)["type"] in ("Partner",):
            continue
        latest = max(a["observed_at"] for a in e.assertions)
        key = (e.confidence, latest)
        if e.src not in best or key > best[e.src][0]:
            best[e.src] = (key, e.dst, e.confidence, e.status)
    children: dict[str, list[tuple[str, float, str]]] = defaultdict(list)
    for src, (_, dst, conf, status) in best.items():
        children[dst].append((src, conf, status))
    ents = {e["id"]: e for e in store.entities()}

    def node(eid: str, conf: float | None, status: str | None, seen: set) -> dict:
        ent = ents.get(eid, {"type": "?", "label": eid, "props": {}})
        kids = [] if eid in seen else [node(c, cf, st, seen | {eid}) for c, cf, st in children.get(eid, [])]
        people = [k for k in kids if k["type"] == "Person"]
        units = [k for k in kids if k["type"] != "Person"]
        units.sort(key=lambda k: -k["headcount"])
        people.sort(key=lambda k: -(k.get("score") or 0))
        headcount = len(people) + sum(k["headcount"] for k in units)
        out = {"id": eid, "type": ent["type"], "label": ent["label"], "confidence": conf, "status": status,
               "headcount": headcount, "children": units + people}
        if ent["type"] == "Person":
            out["score"] = (ent["props"].get("scores") or {}).get("score", 0)
            out["title"] = ent["props"].get("title")
        return out

    return node(root, None, None, set())


def buying_committee(store: Store, problem: Problem, limit_per_role: int = 8) -> dict:
    by_role: dict[str, list[dict]] = defaultdict(list)
    for p in store.entities(NodeType.PERSON):
        props = p["props"]
        for r in props.get("buying_roles") or []:
            by_role[r["role"]].append({
                "id": p["id"], "label": p["label"], "title": props.get("title"), "unit": props.get("unit"),
                "seniority": props.get("seniority"), "confidence": r["confidence"], "rationale": r["rationale"],
                "score": (props.get("scores") or {}).get("score", 0), "scores": props.get("scores"),
                "name_visible": props.get("name_visible"), "profile_url": props.get("profile_url"),
                "notes": props.get("notes") or [],
            })
    out = {}
    for role in ROLE_ORDER:
        people = sorted(by_role.get(role, []), key=lambda x: (-x["score"], -x["confidence"]))
        out[role] = {"count": len(people), "top": people[:limit_per_role]}
    return out


def ranked_people(store: Store, limit: int = 50) -> list[dict]:
    people = []
    for p in store.entities(NodeType.PERSON):
        s = (p["props"].get("scores") or {}).get("score", 0)
        if s:
            people.append({"id": p["id"], "label": p["label"], "title": p["props"].get("title"), "score": s,
                           "roles": [r["role"] for r in p["props"].get("buying_roles") or []],
                           "unit": p["props"].get("unit"), "notes": p["props"].get("notes") or []})
    return sorted(people, key=lambda x: -x["score"])[:limit]


def graph_json(store: Store) -> dict:
    nodes = [{"id": e["id"], "type": e["type"], "label": e["label"], "props": e["props"]} for e in store.entities()]
    edges = []
    for e in store.edges():
        edges.append({
            "id": e.id, "source": e.src, "target": e.dst, "type": e.type, "layer": e.layer,
            "confidence": e.confidence, "status": e.status,
            "assertions": [{"basis": a["basis"], "confidence": a["confidence"], "status": a["status"],
                            "evidence_id": a["evidence_id"], "observed_at": a["observed_at"],
                            "extractor": a["extractor"], "rationale": a["rationale"], "props": a["props"]}
                           for a in e.assertions],
        })
    return {"nodes": nodes, "edges": edges, "evidence": store.evidence(), "stats": store.stats()}


def print_tree(t: dict, indent: int = 0, max_people: int = 4, out=print) -> None:
    pad = "  " * indent
    if t["type"] == "Person":
        return
    conf = f" [{t['status']} {t['confidence']:.2f}]" if t["confidence"] is not None else ""
    out(f"{pad}{t['type']}: {t['label']} ({t['headcount']} people){conf}")
    people = [c for c in t["children"] if c["type"] == "Person"]
    for c in t["children"]:
        if c["type"] != "Person":
            print_tree(c, indent + 1, max_people, out)
    for p in people[:max_people]:
        out(f"{pad}  · {p['label']} — score {p['score']}")
    if len(people) > max_people:
        out(f"{pad}  · … {len(people) - max_people} more")
