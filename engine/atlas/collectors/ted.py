"""Procurement collectors: TED (EU) search API and German OCDS exports (oeffentlichevergabe.de).

Mercedes-Benz is a private company, so it rarely appears as a *buyer* in public tenders.
It does appear as a *supplier/tenderer* (fleet vehicles, after-sales service contracts to
public bodies), which maps its public-sector sales and service organization, and its
subsidiaries and partners appear in consortia. Public buyers that run warranty / fleet
analytics are also prospects in their own right.

Field names in the TED expert query language change between API versions; override them
with ATLAS_TED_FIELDS / the ``query`` argument rather than editing code.
"""
from __future__ import annotations

import json
import os
import re

import httpx

from ..buying import topic_hits
from ..ontology import Basis, EdgeType, NodeType
from ..problems import Problem
from ..store import Store, normalize, slug
from ..targets import mercedes as T

TED_URL = os.environ.get("ATLAS_TED_URL", "https://api.ted.europa.eu/v3/notices/search")
TED_FIELDS = os.environ.get(
    "ATLAS_TED_FIELDS",
    "publication-number,notice-title,buyer-name,buyer-country,winner-name,organisation-name-tenderer,"
    "publication-date,notice-type,classification-cpv,total-value,links",
).split(",")
VERGABE_EXPORT_URL = os.environ.get(
    "ATLAS_VERGABE_URL", "https://oeffentlichevergabe.de/api/notice-exports?pubDay={day}&format=ocds.zip")

MB = re.compile(r"mercedes|daimler ag|mbition|mercedes benz", re.I)


def ted_query_for(problem: Problem) -> str:
    names = " OR ".join(f'"{n}"' for n in ("Mercedes-Benz", "Daimler AG", "MBition", "Mercedes-Benz Tech Innovation"))
    return f"FT ~ ({names})"


def harvest_ted(store: Store, problem: Problem, limit: int = 50, pages: int = 3, query: str | None = None) -> dict:
    q = query or ted_query_for(problem)
    stats = {"calls": 0, "notices": 0, "error": None}
    with httpx.Client(timeout=60) as http:
        for page in range(1, pages + 1):
            body = {"query": q, "fields": TED_FIELDS, "page": page, "limit": limit, "scope": "ALL",
                    "paginationMode": "PAGE_NUMBER"}
            try:
                r = http.post(TED_URL, json=body)
                r.raise_for_status()
            except Exception as e:
                stats["error"] = str(e)[:300]
                break
            data = r.json()
            store.put_raw("ted.search", body, data)
            store.commit()
            stats["calls"] += 1
            notices = data.get("notices") or []
            stats["notices"] += len(notices)
            if len(notices) < limit:
                break
    return stats


def _first(v):
    if isinstance(v, dict):
        # multilingual fields: prefer English, then German, then anything
        for lang in ("eng", "ENG", "en", "deu", "DEU", "de"):
            if lang in v:
                return _first(v[lang])
        return _first(next(iter(v.values()), None))
    if isinstance(v, list):
        return _first(v[0]) if v else None
    return v


def _all(v) -> list[str]:
    if v is None:
        return []
    if isinstance(v, dict):
        out = []
        for x in v.values():
            out += _all(x)
        return out
    if isinstance(v, list):
        out = []
        for x in v:
            out += _all(x)
        return out
    return [str(v)]


def _org(store: Store, name: str) -> str:
    if MB.search(name):
        return T.COMPANY_ID
    hits = store.find_by_alias(name)
    if hits:
        return hits[0]["id"]
    oid = f"org:{slug(name)}"
    store.upsert_entity(oid, NodeType.COMPANY, name, {"source": "procurement"})
    return oid


def build_ted(store: Store, problem: Problem) -> dict:
    store.clear_extractor("procurement")
    stats = {"tenders": 0, "mb_supplier": 0, "mb_buyer": 0, "on_problem": 0}
    for raw in store.raw_documents("ted.search") + store.raw_documents("vergabe.ocds"):
        payload = json.loads(raw["payload"])
        notices = payload.get("notices") or payload.get("releases") or []
        for n in notices:
            if raw["collector"] == "vergabe.ocds":
                parties = n.get("parties") or []
                pub = n.get("ocid") or n.get("id")
                title = (n.get("tender") or {}).get("title") or ""
                buyers = [p["name"] for p in parties if "buyer" in (p.get("roles") or []) and p.get("name")]
                winners = [p["name"] for p in parties if "supplier" in (p.get("roles") or []) and p.get("name")]
                date = (n.get("date") or "")[:10]
                url = f"https://oeffentlichevergabe.de/ui/de/search/details?noticeId={pub}"
            else:
                pub = _first(n.get("publication-number"))
                title = _first(n.get("notice-title")) or ""
                buyers = _all(n.get("buyer-name"))
                winners = _all(n.get("winner-name")) + _all(n.get("organisation-name-tenderer"))
                date = (_first(n.get("publication-date")) or "")[:10]
                url = _first((n.get("links") or {}).get("html")) if isinstance(n.get("links"), dict) else None
                url = url or f"https://ted.europa.eu/en/notice/-/detail/{pub}"
            if not pub:
                continue
            tid = f"tender:{slug(str(pub))}"
            hits = [h for h in topic_hits(problem, title) if h != "analytics"]
            store.upsert_entity(tid, NodeType.TENDER, title[:140] or str(pub),
                                {"publication": pub, "date": date, "buyers": buyers, "winners": winners,
                                 "problem_hits": hits, "url": url})
            evid = store.put_evidence(url=url, title=title or str(pub), basis=Basis.PROCUREMENT_RECORD,
                                      provider="TED" if raw["collector"] == "ted.search" else "oeffentlichevergabe.de",
                                      excerpt=f"Buyer: {', '.join(buyers) or '?'} · Winner/tenderer: {', '.join(winners) or '?'}",
                                      published_at=date or None, raw_document_id=raw["id"])
            for b in dict.fromkeys(buyers):
                bid = _org(store, b)
                stats["mb_buyer"] += bid == T.COMPANY_ID
                store.assert_edge(bid, tid, EdgeType.PROCURED, basis=Basis.PROCUREMENT_RECORD, confidence=0.9,
                                  evidence_id=evid, extractor="procurement", rationale="Named as buyer in the notice.",
                                  observed_at=date or None)
            for w in dict.fromkeys(winners):
                wid = _org(store, w)
                stats["mb_supplier"] += wid == T.COMPANY_ID
                store.assert_edge(tid, wid, EdgeType.AWARDED_TO, basis=Basis.PROCUREMENT_RECORD, confidence=0.85,
                                  evidence_id=evid, extractor="procurement",
                                  rationale="Named as winner/tenderer in the notice.", observed_at=date or None)
            stats["tenders"] += 1
            stats["on_problem"] += bool(hits)
    store.commit()
    return stats
