"""Public web collector: conference programmes, vendor case studies, careers pages, press.

harvest_urls      fetch pages over plain HTTP, store text as raw documents (collector="web.page")
import_web_record ingest a record gathered elsewhere (e.g. by an analyst or a Claude session),
                  optionally with its extraction already attached
build_web         run / replay extraction and write assertions
"""
from __future__ import annotations

import json
import re
from urllib.parse import urlparse

import httpx

from ..buying import topic_hits
from ..extract import Extraction, available, extract_page
from ..ontology import Basis, EdgeType, NodeType
from ..problems import Problem
from ..store import Store, normalize, short_hash, slug
from ..targets import TARGET as T
from ..titles import _match_any

UA = "EnterpriseAtlas/0.2 (+research; contact: repository owner)"
VENDOR_HINTS = ("customers", "case-stud", "cases", "customer-stor", "success-stor", "referenz")
EVENT_HINTS = ("session", "speaker", "agenda", "programme", "program", "conference", "summit", "event")


def guess_basis(url: str) -> Basis:
    host = urlparse(url).netloc.lower()
    path = urlparse(url).path.lower()
    if "mercedes-benz" in host or "daimler" in host:
        return Basis.JOB_AD if ("job" in path or "career" in path or "karriere" in path) else Basis.OFFICIAL_COMPANY
    if "ted.europa.eu" in host or "vergabe" in host:
        return Basis.PROCUREMENT_RECORD
    if "catena-x" in host or "vda.de" in host:
        return Basis.ASSOCIATION
    if any(h in path for h in VENDOR_HINTS):
        return Basis.VENDOR_CLAIM
    if any(h in path or h in host for h in EVENT_HINTS):
        return Basis.EVENT_PROGRAM
    if "github.com" in host or "arxiv" in host or "patent" in host:
        return Basis.PUBLICATION
    return Basis.PRESS


def html_to_text(html: str) -> tuple[str, str]:
    from selectolax.parser import HTMLParser

    tree = HTMLParser(html)
    title = (tree.css_first("title").text(strip=True) if tree.css_first("title") else "")
    for sel in ("script", "style", "noscript", "nav", "footer", "svg"):
        for n in tree.css(sel):
            n.decompose()
    body = tree.body.text(separator="\n", strip=True) if tree.body else ""
    body = re.sub(r"\n{3,}", "\n\n", body)
    return title, body


def harvest_urls(store: Store, urls: list[str]) -> dict:
    stats = {"fetched": 0, "failed": []}
    with httpx.Client(timeout=30, follow_redirects=True, headers={"User-Agent": UA}) as http:
        for url in urls:
            try:
                r = http.get(url)
                r.raise_for_status()
                title, text = html_to_text(r.text)
                store.put_raw("web.page", {"url": url}, {"url": url, "title": title, "text": text,
                                                         "basis": guess_basis(url).value, "status": r.status_code})
                stats["fetched"] += 1
            except Exception as e:  # keep going; record the failure
                stats["failed"].append({"url": url, "error": str(e)[:200]})
    store.commit()
    return stats


def import_web_record(store: Store, rec: dict) -> str:
    """rec: {kind:'web', url, title, basis?, text?, excerpt?, published_at?, extracted?, observed_at?, provider?}"""
    payload = {k: rec.get(k) for k in ("url", "title", "text", "excerpt", "basis", "published_at", "extracted",
                                        "provider", "observed_at", "note")}
    payload["basis"] = payload["basis"] or guess_basis(rec["url"]).value
    return store.put_raw("web.page", {"url": rec["url"]}, payload)


# ------------------------------------------------------------------ resolution
ORG_TYPES = (NodeType.COMPANY, NodeType.BUSINESS_UNIT, NodeType.PARTNER)


def resolve(store: Store, ent: dict) -> str:
    if ent.get("id"):
        return ent["id"]
    t = NodeType(ent["type"])
    name = ent["name"].strip()
    if t == NodeType.PERSON:
        hits = store.find_by_alias(name, NodeType.PERSON)
        if len(hits) == 1:
            return hits[0]["id"]
        return f"person:name:{slug(name)}"
    if t in ORG_TYPES:
        for ot in ORG_TYPES:
            hits = store.find_by_alias(name, ot)
            if hits:
                return hits[0]["id"]
        if _match_any(T.EMPLOYER_PATTERNS, normalize(name)):
            return T.COMPANY_ID
        return f"{'partner' if t == NodeType.PARTNER else 'org'}:{slug(name)}"
    if t in (NodeType.TEAM, NodeType.FUNCTION, NodeType.TECHNOLOGY, NodeType.TOPIC, NodeType.EVENT, NodeType.PROJECT):
        hits = store.find_by_alias(name, t)
        if len(hits) == 1:
            return hits[0]["id"]
    return f"{t.value.lower()}:{slug(name)}"


def apply_extraction(store: Store, x: Extraction, page: dict, raw_id: str, problem: Problem, extractor: str) -> dict:
    basis = Basis(x.basis)
    observed = page.get("observed_at") or None
    ids: dict[str, str] = {}
    for e in x.entities:
        eid = resolve(store, e.model_dump())
        ids[e.key] = eid
        existing = store.entity(eid)
        props = {"description": e.description, "affiliation": e.affiliation}
        if e.type == "Person":
            props.update({"title": e.title, "name_visible": True})
        store.upsert_entity(eid, existing and NodeType(existing["type"]) or NodeType(e.type),
                            existing["label"] if existing else e.name, props, [e.name])
    n = 0
    for r in x.relations:
        if r.source_key not in ids or r.target_key not in ids:
            continue
        evid = store.put_evidence(url=page["url"], title=page.get("title") or page["url"], basis=basis,
                                  provider=page.get("provider") or "web", excerpt=r.quote,
                                  locator=f"quote:{short_hash(r.quote)}", published_at=x.published_date,
                                  raw_document_id=raw_id, observed_at=observed)
        if r.type == "WORKS_IN":
            src_ent = store.entity(ids[r.source_key])
            if src_ent and src_ent["type"] == "Person" and not src_ent["props"].get("unit"):
                store.upsert_entity(src_ent["id"], NodeType.PERSON, src_ent["label"], {"unit": ids[r.target_key]})
        store.assert_edge(ids[r.source_key], ids[r.target_key], EdgeType(r.type), basis=basis,
                          confidence=r.confidence, evidence_id=evid, extractor=extractor, rationale=r.quote,
                          observed_at=observed)
        n += 1
    return {"entities": len(ids), "relations": n}


def build_web(store: Store, problem: Problem) -> dict:
    store.clear_extractor("web-extraction")
    store.clear_extractor("web-activity")
    cached = {json.loads(r["request"])["page"]: r for r in store.raw_documents("llm.extraction")}
    stats = {"pages": 0, "extracted": 0, "pending_llm": 0, "relations": 0}
    for raw in store.raw_documents("web.page"):
        page = json.loads(raw["payload"])
        stats["pages"] += 1
        x = None
        if page.get("extracted"):
            x = Extraction.model_validate(page["extracted"])
        elif raw["id"] in cached:
            x = Extraction.model_validate(json.loads(cached[raw["id"]]["payload"]))
        elif page.get("text") and available():
            x = extract_page(page["text"][:150_000], page["url"], page.get("title") or "", problem.description)
            if x:
                store.put_raw("llm.extraction", {"page": raw["id"]}, x.model_dump())
        if not x:
            stats["pending_llm"] += 1
            continue
        res = apply_extraction(store, x, page, raw["id"], problem, "web-extraction")
        stats["extracted"] += 1
        stats["relations"] += res["relations"]

    # activity -> champion hypotheses: a person who spoke about / contributed to something on-problem
    topic = problem.topic_id
    store.upsert_entity(topic, NodeType.TOPIC, problem.label, {"problem": problem.id})
    ents = {e["id"]: e for e in store.entities()}
    bonus: dict[str, float] = {}
    for e in store.edges("type IN ('SPOKE_ABOUT','CONTRIBUTED_TO','SPOKE_AT','WORKS_ON','MEMBER_OF') AND extractor='web-extraction'"):
        src, dst = ents.get(e.src), ents.get(e.dst)
        if not src or not dst or src["type"] != "Person":
            continue
        text = " ".join([dst["label"], dst["props"].get("description") or ""])
        hits = [h for h in topic_hits(problem, text) if h != "analytics"]
        if not hits and dst["id"] != topic:
            continue
        ev = e.assertions[0]["evidence_id"]
        store.assert_edge(e.src, topic, EdgeType.INFLUENCES, basis=Basis.HEURISTIC, confidence=0.5, evidence_id=ev,
                          extractor="web-activity", props={"buying_role": "champion"},
                          rationale=f"Publicly active on '{dst['label']}' ({', '.join(hits) or 'topic'}). "
                                    "Shows subject-matter involvement, not authority.")
        bonus[e.src] = bonus.get(e.src, 0) + 0.25
    for pid, b in bonus.items():
        p = store.entity(pid)
        roles = [r for r in (p["props"].get("buying_roles") or []) if r["role"] != "champion"]
        roles.append({"role": "champion", "confidence": 0.5,
                      "rationale": "Public talk / contribution on the problem topic."})
        scores = dict(p["props"].get("scores") or {})
        base = scores.get("base", 40)
        scores.update({"score": min(99, base + round(15 * min(b, 0.5) / 0.5)), "activity": round(min(1, b) * 100)})
        store.upsert_entity(pid, NodeType.PERSON, p["label"], {"buying_roles": roles, "scores": scores})
    store.commit()
    return stats
