"""Builders: replay raw collector documents into entities and assertions.

Builders are deterministic and idempotent. Each one owns an ``extractor`` name; a rebuild
deletes that extractor's assertions and replays every raw document. Raw documents are
never deleted, so the graph can always be regenerated with improved parsing rules.
"""
from __future__ import annotations

import json
import re
from collections import Counter

from .buying import ROLE_EDGE, infer_roles, score_person, topic_hits
from .ontology import Basis, EdgeType, NodeType
from .problems import Problem
from .store import Store, normalize, slug
from .targets import mercedes as T
from .titles import FUNCTIONS, SUBFUNCTIONS, _match_any, parse_title

ANON = {"linkedin member", ""}


# --------------------------------------------------------------------- seed
def build_seed(store: Store) -> None:
    store.clear_extractor("seed")
    ev = {}
    for key, s in T.SOURCES.items():
        ev[key] = store.put_evidence(url=s["url"], title=s["title"], basis=Basis(s["basis"]),
                                     provider=s["provider"], excerpt=s["excerpt"], access=s.get("access", "public"),
                                     observed_at=T.OBSERVED)
    for eid, typ, label, aliases in T.UNITS:
        store.upsert_entity(eid, NodeType(typ), label, {"seed": True}, aliases)
    for child, parent, src, conf in T.STRUCTURE:
        store.assert_edge(child, parent, EdgeType.BELONGS_TO, basis=Basis.OFFICIAL_COMPANY, confidence=conf,
                          evidence_id=ev[src], extractor="seed", rationale=T.SOURCES[src]["excerpt"],
                          observed_at=T.OBSERVED)
    for child, parent in T.UNIT_PARENTS.items():
        store.assert_edge(child, parent, EdgeType.BELONGS_TO, basis=Basis.HEURISTIC, confidence=0.5, evidence_id=None,
                          extractor="seed", rationale="Mercedes-Benz-branded unit; legal parent not yet sourced. Add an "
                          "annual-report citation to confirm.")
    for name, role in T.BOARD:
        pid = f"person:name:{slug(name)}"
        store.upsert_entity(pid, NodeType.PERSON, name, {"title": role, "seniority": "board", "name_visible": True,
                                                         "functions": [], "unit": T.COMPANY_ID})
        store.assert_edge(pid, T.COMPANY_ID, EdgeType.WORKS_IN, basis=Basis.OFFICIAL_COMPANY, confidence=0.95,
                          evidence_id=ev["linkedin_company"], extractor="seed",
                          rationale=f"Listed in the company imprint as: {role}.", observed_at=T.OBSERVED)


# ------------------------------------------------------- org placement helpers
def _unit_for(tp) -> tuple[str, list[str]]:
    notes = []
    units = [u for u in tp.unit_hints if u != "org:daimler-truck"]
    if "org:daimler-truck" in tp.unit_hints and not units:
        notes.append("Title mentions trucks/buses: since the 2021 spin-off these belong to Daimler Truck, "
                     "so this Mercedes-Benz affiliation may be stale.")
        return "org:daimler-truck", notes
    if tp.historic_employer:
        notes.append("Employer given as 'Daimler AG' (pre-2022 name); affiliation may be stale.")
    if "bu:mb-cars" in units and "bu:mb-vans" in units:
        units.remove("bu:mb-vans")  # "vans" often appears as a product, cars wins when both
    return (units[0] if units else "bu:mb-ag"), notes


def ensure_function(store: Store, unit: str, fn: str) -> str:
    fid = f"fn:{unit.split(':', 1)[1]}:{fn}"
    unit_label = (store.entity(unit) or {}).get("label", unit)
    store.upsert_entity(fid, NodeType.FUNCTION, FUNCTIONS[fn][0], {"unit": unit, "function": fn,
                                                                    "unit_label": unit_label})
    return fid


def ensure_team(store: Store, unit: str, sub: str) -> tuple[str, str]:
    parent_fn, label, _ = SUBFUNCTIONS[sub]
    fid = ensure_function(store, unit, parent_fn)
    tid = f"team:{unit.split(':', 1)[1]}:{sub}"
    store.upsert_entity(tid, NodeType.TEAM, label, {"unit": unit, "function": parent_fn, "subfunction": sub})
    return tid, fid


def _is_target_employer(tp) -> bool:
    if not tp.employer_hint:
        return True  # people search is already scoped to the target's LinkedIn company
    return _match_any(T.EMPLOYER_PATTERNS, normalize(tp.employer_hint))


# -------------------------------------------------------------- needle people
def person_id(hit: dict) -> str:
    if hit.get("publicIdentifier"):
        return f"person:li:{slug(hit['publicIdentifier'], 96)}"
    m = re.search(r"/in/([^/?#]+)", hit.get("profileUrl") or "")
    return f"person:li:{m.group(1) if m else slug(hit.get('headline') or 'unknown')}"


def build_needle_people(store: Store, problem: Problem) -> dict:
    """Place every LinkedIn person hit in the org graph and add buying-role hypotheses."""
    store.clear_extractor("needle-people")
    store.clear_extractor("buying-heuristic")
    topic = problem.topic_id
    store.upsert_entity(topic, NodeType.TOPIC, problem.label, {"description": problem.description, "problem": problem.id})
    stats = Counter()
    seen_evidence: dict[str, set[str]] = {}

    for raw in store.raw_documents("needle.people_search"):
        request = json.loads(raw["request"])
        payload = json.loads(raw["payload"])
        query_label = request.get("label") or json.dumps(request.get("params", {}), ensure_ascii=False)
        for hit in payload.get("hits", []):
            headline = (hit.get("headline") or "").strip()
            if not headline or headline == "--":
                stats["skipped_no_headline"] += 1
                continue
            tp = parse_title(headline, T.UNIT_LEXICON, problem.topics)
            pid = person_id(hit)
            name = (hit.get("fullName") or "").strip()
            visible = normalize(name) not in ANON
            label = name if visible else f"{tp.title[:60]} (name hidden)"
            evid = store.put_evidence(
                url=hit.get("profileUrl") or "https://www.linkedin.com/", title=headline, basis=Basis.SELF_REPORTED_PROFILE,
                provider="Needle/LinkedIn", access="licensed", excerpt=" · ".join(filter(None, [headline, hit.get("location")])),
                locator=f"people search: {query_label}", raw_document_id=raw["id"], observed_at=raw["fetched_at"][:10],
            )
            seen_evidence.setdefault(pid, set()).add(evid)
            target_emp = _is_target_employer(tp)
            unit, notes = _unit_for(tp)
            alumni = False
            if not target_emp and not tp.external:
                # Company-scoped search returned someone whose headline names another employer:
                # most likely a former employee or stale profile, not a partner.
                alumni = True
                notes.append(f"Headline names '{tp.employer_hint}' as employer; likely former Mercedes-Benz "
                             "employee (alumni route), not a current one.")

            props = {
                "headline": headline, "title": tp.title, "location": hit.get("location"), "degree": hit.get("degree"),
                "profile_url": hit.get("profileUrl"), "image_url": hit.get("imageUrl"), "name_visible": visible,
                "seniority": tp.seniority, "functions": tp.functions, "subfunctions": tp.subfunctions,
                "unit": unit, "external": tp.external, "employer_hint": tp.employer_hint, "notes": notes,
                "public_identifier": hit.get("publicIdentifier"),
            }
            store.upsert_entity(pid, NodeType.PERSON, label, props, [name] if visible else [])
            stats["people"] += 1

            if alumni:
                org = f"org:{slug(tp.employer_hint)}"
                store.upsert_entity(org, NodeType.COMPANY, tp.employer_hint, {"source": "headline"})
                store.assert_edge(pid, org, EdgeType.WORKS_IN, basis=Basis.SELF_REPORTED_PROFILE, confidence=0.7,
                                  evidence_id=evid, extractor="needle-people", rationale=f"Self-reported headline: “{headline}”.")
                store.upsert_entity(pid, NodeType.PERSON, label, {"alumni": True})
                stats["alumni"] += 1
            elif tp.external:
                partner = tp.employer_hint or "Unknown partner"
                partner_id = f"partner:{slug(partner)}"
                store.upsert_entity(partner_id, NodeType.PARTNER, partner, {"source": "headline"})
                store.assert_edge(pid, partner_id, EdgeType.WORKS_IN, basis=Basis.SELF_REPORTED_PROFILE, confidence=0.6,
                                  evidence_id=evid, extractor="needle-people", rationale="Employer named in headline.")
                store.assert_edge(partner_id, T.COMPANY_ID, EdgeType.PARTNERS_WITH, basis=Basis.SELF_REPORTED_PROFILE,
                                  confidence=0.4, evidence_id=evid, extractor="needle-people",
                                  rationale="An employee's headline describes delivery work for Mercedes-Benz.")
                stats["external"] += 1
            else:
                # place: unit -> function -> team
                fn = tp.primary_function
                subs = [s for s in tp.subfunctions if SUBFUNCTIONS[s][0] in tp.functions]
                placed = unit
                if fn:
                    fid = ensure_function(store, unit, fn)
                    store.assert_edge(fid, unit, EdgeType.BELONGS_TO, basis=Basis.SELF_REPORTED_PROFILE, confidence=0.35,
                                      evidence_id=evid, extractor="needle-people",
                                      rationale="Inferred from an employee headline naming this function in this unit.")
                    placed = fid
                    sub = next((s for s in subs if SUBFUNCTIONS[s][0] == fn), subs[0] if subs else None)
                    if sub:
                        tid, parent_fid = ensure_team(store, unit, sub)
                        store.assert_edge(tid, parent_fid, EdgeType.BELONGS_TO, basis=Basis.SELF_REPORTED_PROFILE,
                                          confidence=0.35, evidence_id=evid, extractor="needle-people",
                                          rationale="Inferred from an employee headline naming this team.")
                        if parent_fid != fid:
                            store.assert_edge(parent_fid, unit, EdgeType.BELONGS_TO, basis=Basis.SELF_REPORTED_PROFILE,
                                              confidence=0.35, evidence_id=evid, extractor="needle-people",
                                              rationale="Inferred from an employee headline.")
                        placed = tid
                store.assert_edge(pid, placed, EdgeType.WORKS_IN, basis=Basis.SELF_REPORTED_PROFILE,
                                  confidence=0.75 if not notes else 0.5, evidence_id=evid, extractor="needle-people",
                                  rationale=f"Self-reported headline: “{headline}”." + (" " + " ".join(notes) if notes else ""))
                stats["placed"] += 1

            # topical involvement stated in the headline itself
            hits = topic_hits(problem, headline)
            domain_hits = [h for h in hits if h != "analytics"]
            if domain_hits:
                store.assert_edge(pid, topic, EdgeType.WORKS_ON, basis=Basis.SELF_REPORTED_PROFILE, confidence=0.55,
                                  evidence_id=evid, extractor="needle-people",
                                  rationale=f"Headline mentions: {', '.join(hits)}.")

            # buying-role hypotheses
            roles = infer_roles(tp, problem) if not alumni else []
            if alumni:
                from .buying import RoleHypothesis
                from .ontology import BuyingRole
                roles = [RoleHypothesis(BuyingRole.INTRODUCER, 0.3,
                                        "Likely Mercedes-Benz alumni; may know the current team and route an introduction.")]
            for r in roles:
                target = T.COMPANY_ID if r.role.value == "introducer" else topic
                store.assert_edge(pid, target, ROLE_EDGE[r.role], basis=Basis.HEURISTIC, confidence=r.confidence,
                                  evidence_id=evid, extractor="buying-heuristic", rationale=r.rationale,
                                  props={"buying_role": r.role.value})
            scores = score_person(roles, tp, problem, hit.get("degree"), visible, len(seen_evidence[pid]))
            scores["base"] = scores["score"]
            store.upsert_entity(pid, NodeType.PERSON, label, {
                "buying_roles": [{"role": r.role.value, "confidence": r.confidence, "rationale": r.rationale} for r in roles],
                "scores": scores,
            })
            stats["with_roles"] += bool(roles)
    store.commit()
    return dict(stats)
