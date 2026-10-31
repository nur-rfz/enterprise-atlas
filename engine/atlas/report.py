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


def entry_paths(store: Store, problem: Problem) -> list[dict]:
    """Suggested routes into the buying committee, each step a ranked, evidence-backed person."""
    import re

    c = buying_committee(store, problem, limit_per_role=25)
    paths = []

    def pick(role, used, prefer=None):
        cands = [p for p in c[role]["top"] if p["id"] not in used]
        if prefer:
            pref = [p for p in cands if re.search(prefer, (p.get("title") or "") + " " + p["label"], re.I)]
            cands = pref or cands
        cands.sort(key=lambda p: -(p["confidence"] * (p["score"] or 1)))
        if cands:
            used.add(cands[0]["id"])
            return {**cands[0], "_role": role}
        return None

    def add(title, why, kind, plan):
        used: set = set()
        steps = [pick(r, used, pref) for r, pref in plan]
        steps = [s for s in steps if s]
        if len(steps) >= 2:
            paths.append({"title": title, "why": why, "kind": kind,
                          "steps": [{"id": s["id"], "label": s["label"], "title": s.get("title"), "role": s["_role"],
                                     "rationale": s["rationale"]} for s in steps]})

    add("Bottom-up through the data team",
        "Start where the tool gets evaluated. A data/analytics lead embedded in the domain can run a pilot and carry it to the business owner.",
        "technical", [("evaluator", None), ("problem_owner", "warranty|garantie|quality|qualit"), ("business_sponsor", None)])
    add("Champion first",
        "Someone already speaking publicly about the problem is the warmest first conversation; use their talk as the opener.",
        "champion", [("champion", None), ("evaluator", None), ("business_sponsor", None)])
    add("Warm introduction",
        "Partners delivering on the account, alumni and leadership assistants route introductions without a cold approach.",
        "intro", [("introducer", "assistant"), ("problem_owner", None), ("business_sponsor", None)])
    add("Formal vendor route",
        "Register with the software category manager early so procurement is not the blocker once the business says yes.",
        "formal", [("procurement", r"software|\bit\b"), ("technical_approver", "after ?sales"), ("business_sponsor", None)])
    return paths


def signals(store: Store, limit: int = 40) -> list[dict]:
    """Off-LinkedIn evidence: the hidden intelligence layer."""
    skip = {"self_reported_profile", "heuristic"}
    counts = {r[0]: r[1] for r in store.db.execute("SELECT evidence_id, COUNT(*) FROM assertions GROUP BY evidence_id")}
    rows = [dict(e, claims=counts.get(e["id"], 0)) for e in store.evidence() if e["basis"] not in skip]
    seen, out = set(), []
    for r in sorted(rows, key=lambda r: (r["basis"] == "official_company", -(r["claims"]))):
        if r["url"] in seen:
            continue
        seen.add(r["url"])
        out.append({k: r[k] for k in ("id", "url", "title", "excerpt", "basis", "provider", "published_at", "observed_at", "claims")})
    return out[:limit]


def explain(store: Store, problem: Problem) -> dict:
    """Everything the 'How it works' view needs, computed from the live code and data."""
    from .buying import REACHABILITY, ROLE_WEIGHT, infer_roles, topic_hits
    from .ontology import (ESTABLISHES, LAYER_OF, MAX_CONFIDENCE_BY_BASIS, UNSUPPORTED_CEILING, Basis, EdgeType,
                           NodeType as NT)
    from .targets import TARGET as T
    from .titles import parse_title

    people = store.entities(NT.PERSON)
    by_head = {p["props"].get("headline"): p for p in people if p["props"].get("headline")}

    def parse_example(headline):
        tp = parse_title(headline, T.UNIT_LEXICON, problem.topics)
        p = by_head.get(headline)
        return {"headline": headline, "title": tp.title, "employer": tp.employer_hint, "seniority": tp.seniority,
                "functions": tp.functions, "subfunctions": tp.subfunctions, "units": tp.unit_hints,
                "topics": topic_hits(problem, headline), "external": tp.external,
                "roles": [{"role": r.role.value, "confidence": r.confidence, "rationale": r.rationale}
                          for r in infer_roles(tp, problem)],
                "person": p and {"id": p["id"], "label": p["label"], "unit": p["props"].get("unit"),
                                 "score": (p["props"].get("scores") or {}).get("score")}}

    wanted = [
        "Director of Service & Parts Business and Warranty & Goodwill Mercedes-Benz Cars bei Mercedes-Benz AG",
        "Team Lead Data, AI & Analytics After-Sales at Mercedes-Benz AG",
        "Senior Manager | Lead Field Quality Software & OTA at MB.OS",
        "Garantie & Kulanz Controllerin bei Mercedes-Benz AG",
        "Global Software Category Manager - IT Procurement Mercedes-Benz Group AG",
        "Executive Assistant to the Head of Van Customer Service & Parts bei Mercedes-Benz AG",
    ]
    placement = [parse_example(h) for h in wanted if h in by_head] or [parse_example(h) for h in list(by_head)[:5]]

    hygiene = []
    for p in people:
        pr = p["props"]
        kind = None
        if pr.get("alumni"):
            kind = "alumni"
        elif pr.get("external"):
            kind = "partner"
        elif any("stale" in n for n in pr.get("notes") or []):
            kind = "stale"
        if pr.get("merged_from"):
            hygiene.append({"kind": "merged", "id": p["id"], "label": p["label"], "headline": pr.get("headline"),
                            "note": f"Seen anonymously as “LinkedIn Member” in another search; same headline and location, merged into one person."})
        if kind:
            hygiene.append({"kind": kind, "id": p["id"], "label": p["label"], "headline": pr.get("headline"),
                            "note": " ".join(pr.get("notes") or []) or ("Delivery partner on the account." if kind == "partner" else "")})

    # a corroborated edge to show the confidence math
    sample = None
    for e in sorted(store.edges("type='BELONGS_TO'"), key=lambda e: -len({a['evidence_id'] for a in e.assertions})):
        if len(e.assertions) >= 3:
            ents = {x: store.entity(x) for x in (e.src, e.dst)}
            sample = {"src": ents[e.src]["label"], "dst": ents[e.dst]["label"], "type": e.type, "confidence": e.confidence,
                      "status": e.status, "n": len(e.assertions),
                      "each": [a["confidence"] for a in e.assertions][:8], "basis": e.assertions[0]["basis"]}
            break

    # hidden intelligence example: job-ad-backed structure
    hidden = []
    for e in store.edges():
        bases = {a["basis"] for a in e.assertions}
        if bases & {"job_ad", "event_program", "vendor_claim", "association", "procurement_record"}:
            src, dst = store.entity(e.src), store.entity(e.dst)
            ev = store.evidence([a["evidence_id"] for a in e.assertions if a["evidence_id"]])
            hidden.append({"src": src["label"], "src_type": src["type"], "dst": dst["label"], "dst_type": dst["type"],
                           "type": e.type, "basis": sorted(bases)[0], "confidence": e.confidence,
                           "quote": e.assertions[0]["rationale"], "url": ev[0]["url"] if ev else None,
                           "source": ev[0]["title"] if ev else None})
    order = {"BELONGS_TO": 0, "USES_TECH": 1, "HIRING_FOR": 2, "SPOKE_ABOUT": 3, "CONTRIBUTED_TO": 4}
    hidden.sort(key=lambda h: (order.get(h["type"], 9), -h["confidence"]))

    return {
        "node_types": [n.value for n in NT],
        "edge_types": [{"type": t.value, "layer": LAYER_OF[t].value} for t in EdgeType],
        "bases": [{"basis": b.value, "ceiling": MAX_CONFIDENCE_BY_BASIS[b],
                   "establishes": sorted(t.value for t in ESTABLISHES[b]) if b != Basis.ANALYST else ["any"]}
                  for b in Basis],
        "unsupported_ceiling": UNSUPPORTED_CEILING,
        "role_weights": {r.value: w for r, w in ROLE_WEIGHT.items()},
        "reachability": {str(k): v for k, v in REACHABILITY.items()},
        "placement": placement, "hygiene": hygiene[:12], "confidence_example": sample, "hidden": hidden[:8],
        "counts": store.stats(),
    }
