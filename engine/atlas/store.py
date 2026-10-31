"""SQLite-backed ontology store.

Tables
------
raw_documents  every collector response, verbatim, so any assertion can be re-derived
evidence       a citable unit (URL + locator) derived from a raw document
entities       typed nodes with JSON properties
aliases        normalized alternative names -> entity (used by resolution)
assertions     one claim, by one piece of evidence, about one typed relationship

Edges are never stored directly: they are aggregated from assertions on read, so
corroboration and contradiction stay visible.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .ontology import (LAYER_OF, MAX_CONFIDENCE_BY_BASIS, UNSUPPORTED_CEILING, Basis, EdgeType, NodeType,
                       clamp_confidence, combine)

SCHEMA = """
CREATE TABLE IF NOT EXISTS raw_documents (
  id TEXT PRIMARY KEY,
  collector TEXT NOT NULL,
  request TEXT NOT NULL,
  payload TEXT NOT NULL,
  fetched_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS evidence (
  id TEXT PRIMARY KEY,
  url TEXT NOT NULL,
  title TEXT NOT NULL,
  excerpt TEXT NOT NULL DEFAULT '',
  locator TEXT NOT NULL DEFAULT '',
  basis TEXT NOT NULL,
  provider TEXT NOT NULL,
  access TEXT NOT NULL DEFAULT 'public',
  observed_at TEXT NOT NULL,
  published_at TEXT,
  raw_document_id TEXT REFERENCES raw_documents(id)
);
CREATE TABLE IF NOT EXISTS entities (
  id TEXT PRIMARY KEY,
  type TEXT NOT NULL,
  label TEXT NOT NULL,
  props TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS entities_type ON entities(type);
CREATE TABLE IF NOT EXISTS aliases (
  alias TEXT NOT NULL,
  entity_id TEXT NOT NULL REFERENCES entities(id),
  PRIMARY KEY (alias, entity_id)
);
CREATE TABLE IF NOT EXISTS assertions (
  id TEXT PRIMARY KEY,
  src TEXT NOT NULL REFERENCES entities(id),
  dst TEXT NOT NULL REFERENCES entities(id),
  type TEXT NOT NULL,
  basis TEXT NOT NULL,
  confidence REAL NOT NULL,
  status TEXT NOT NULL,
  evidence_id TEXT REFERENCES evidence(id),
  observed_at TEXT NOT NULL,
  extractor TEXT NOT NULL,
  rationale TEXT NOT NULL DEFAULT '',
  props TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS assertions_src ON assertions(src);
CREATE INDEX IF NOT EXISTS assertions_dst ON assertions(dst);
CREATE INDEX IF NOT EXISTS assertions_type ON assertions(type);
CREATE TABLE IF NOT EXISTS merges (src TEXT PRIMARY KEY, dst TEXT NOT NULL, merged_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS rejections (
  src TEXT NOT NULL, dst TEXT NOT NULL, type TEXT NOT NULL, evidence_id TEXT, reason TEXT, rejected_at TEXT NOT NULL,
  PRIMARY KEY (src, dst, type, evidence_id)
);
"""


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def today() -> str:
    return date.today().isoformat()


def normalize(text: str) -> str:
    """Lowercase, fold umlauts/accents, collapse punctuation. 'Jörg' == 'joerg' == 'jorg'."""
    t = text.lower().replace("ß", "ss").replace("ä", "ae").replace("ö", "oe").replace("ü", "ue")
    t = unicodedata.normalize("NFKD", t)
    t = "".join(ch for ch in t if not unicodedata.combining(ch))
    out = []
    for ch in t:
        out.append(ch if ch.isalnum() else " ")
    return " ".join("".join(out).split())


def slug(text: str, limit: int = 64) -> str:
    return normalize(text).replace(" ", "-")[:limit] or "x"


def short_hash(*parts: Any) -> str:
    h = hashlib.sha1("\x1f".join(json.dumps(p, sort_keys=True, default=str) for p in parts).encode())
    return h.hexdigest()[:16]


@dataclass
class Edge:
    src: str
    dst: str
    type: str
    layer: str
    confidence: float
    status: str
    assertions: list[dict] = field(default_factory=list)

    @property
    def id(self) -> str:
        return f"{self.src}|{self.type}|{self.dst}"


class Store:
    def __init__(self, path: str | Path = ":memory:"):
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.path)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)

    # ------------------------------------------------------------------ raw
    def put_raw(self, collector: str, request: Any, payload: Any) -> str:
        rid = f"raw:{collector}:{short_hash(collector, request, payload)}"
        self.db.execute(
            "INSERT OR IGNORE INTO raw_documents(id, collector, request, payload, fetched_at) VALUES (?,?,?,?,?)",
            (rid, collector, json.dumps(request, default=str), json.dumps(payload, default=str), now_iso()),
        )
        return rid

    def raw_documents(self, collector: str | None = None) -> list[sqlite3.Row]:
        if collector:
            return self.db.execute("SELECT * FROM raw_documents WHERE collector=? ORDER BY fetched_at", (collector,)).fetchall()
        return self.db.execute("SELECT * FROM raw_documents ORDER BY fetched_at").fetchall()

    # ------------------------------------------------------------- evidence
    def put_evidence(
        self,
        *,
        url: str,
        title: str,
        basis: Basis,
        provider: str,
        excerpt: str = "",
        locator: str = "",
        access: str = "public",
        observed_at: str | None = None,
        published_at: str | None = None,
        raw_document_id: str | None = None,
    ) -> str:
        eid = f"ev:{short_hash(url, locator)}"
        self.db.execute(
            """INSERT INTO evidence(id,url,title,excerpt,locator,basis,provider,access,observed_at,published_at,raw_document_id)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(id) DO UPDATE SET title=excluded.title, excerpt=excluded.excerpt,
                 observed_at=excluded.observed_at, raw_document_id=COALESCE(excluded.raw_document_id, evidence.raw_document_id)""",
            (eid, url, title[:400], excerpt[:2000], locator, basis.value, provider, access,
             observed_at or today(), published_at, raw_document_id),
        )
        return eid

    def evidence(self, ids: Iterable[str] | None = None) -> list[dict]:
        if ids is None:
            rows = self.db.execute("SELECT * FROM evidence").fetchall()
        else:
            ids = list(ids)
            if not ids:
                return []
            q = ",".join("?" * len(ids))
            rows = self.db.execute(f"SELECT * FROM evidence WHERE id IN ({q})", ids).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------- entities
    def upsert_entity(self, eid: str, type: NodeType, label: str, props: dict | None = None,
                      aliases: Iterable[str] = ()) -> str:
        row = self.db.execute("SELECT props FROM entities WHERE id=?", (eid,)).fetchone()
        ts = now_iso()
        if row:
            merged = {**json.loads(row["props"]), **{k: v for k, v in (props or {}).items() if v not in (None, "", [])}}
            self.db.execute("UPDATE entities SET label=?, props=?, updated_at=? WHERE id=?",
                            (label, json.dumps(merged), ts, eid))
        else:
            self.db.execute("INSERT INTO entities(id,type,label,props,created_at,updated_at) VALUES (?,?,?,?,?,?)",
                            (eid, type.value, label, json.dumps(props or {}), ts, ts))
        for a in {label, *aliases}:
            if a:
                self.db.execute("INSERT OR IGNORE INTO aliases(alias, entity_id) VALUES (?,?)", (normalize(a), eid))
        return eid

    def entity(self, eid: str) -> dict | None:
        row = self.db.execute("SELECT * FROM entities WHERE id=?", (eid,)).fetchone()
        return self._entity(row) if row else None

    def entities(self, type: NodeType | None = None) -> list[dict]:
        if type:
            rows = self.db.execute("SELECT * FROM entities WHERE type=?", (type.value,)).fetchall()
        else:
            rows = self.db.execute("SELECT * FROM entities").fetchall()
        return [self._entity(r) for r in rows]

    def find_by_alias(self, name: str, type: NodeType | None = None) -> list[dict]:
        rows = self.db.execute(
            "SELECT e.* FROM aliases a JOIN entities e ON e.id=a.entity_id WHERE a.alias=?" + (" AND e.type=?" if type else ""),
            (normalize(name), type.value) if type else (normalize(name),),
        ).fetchall()
        return [self._entity(r) for r in rows]

    @staticmethod
    def _entity(row: sqlite3.Row) -> dict:
        d = dict(row)
        d["props"] = json.loads(d["props"])
        return d

    # ----------------------------------------------------------- assertions
    def assert_edge(
        self,
        src: str,
        dst: str,
        type: EdgeType,
        *,
        basis: Basis,
        confidence: float,
        evidence_id: str | None,
        extractor: str,
        rationale: str = "",
        observed_at: str | None = None,
        props: dict | None = None,
    ) -> str | None:
        if src == dst:
            return None
        if basis not in (Basis.HEURISTIC, Basis.ANALYST) and not evidence_id:
            raise ValueError("Non-heuristic assertions require evidence")
        conf, status = clamp_confidence(type, basis, confidence)
        aid = f"as:{short_hash(src, dst, type.value, evidence_id, extractor)}"
        self.db.execute(
            """INSERT INTO assertions(id,src,dst,type,basis,confidence,status,evidence_id,observed_at,extractor,rationale,props)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(id) DO UPDATE SET confidence=excluded.confidence, status=excluded.status,
                  observed_at=excluded.observed_at, rationale=excluded.rationale, props=excluded.props""",
            (aid, src, dst, type.value, basis.value, conf, status, evidence_id, observed_at or today(),
             extractor, rationale, json.dumps(props or {})),
        )
        return aid

    def clear_extractor(self, extractor: str) -> None:
        """Remove derived assertions so a deterministic stage can be re-run idempotently."""
        self.db.execute("DELETE FROM assertions WHERE extractor=?", (extractor,))

    def assertions(self, where: str = "1=1", params: tuple = ()) -> list[dict]:
        rows = self.db.execute(f"SELECT * FROM assertions WHERE {where}", params).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["props"] = json.loads(d["props"])
            out.append(d)
        return out

    def edges(self, where: str = "1=1", params: tuple = ()) -> list[Edge]:
        groups: dict[tuple[str, str, str], list[dict]] = {}
        for a in self.assertions(where, params):
            groups.setdefault((a["src"], a["dst"], a["type"]), []).append(a)
        out: list[Edge] = []
        for (src, dst, t), items in groups.items():
            # independent evidence only: one vote per evidence id
            by_ev: dict[str, float] = {}
            for a in items:
                key = a["evidence_id"] or a["id"]
                by_ev[key] = max(by_ev.get(key, 0.0), a["confidence"])
            conf = combine(list(by_ev.values()))
            statuses = {a["status"] for a in items}
            n = len(by_ev)
            if "confirmed" in statuses:
                status = "confirmed"
            elif "inferred" in statuses:
                # heuristic-only edges stay below the heuristic ceiling however often they repeat
                status, conf = "inferred", min(conf, MAX_CONFIDENCE_BY_BASIS[Basis.HEURISTIC])
            else:
                # weak claims corroborated by independent sources earn limited confidence
                conf = min(conf, UNSUPPORTED_CEILING + 0.08 * (n - 1), 0.8)
                status = "inferred" if n >= 3 else "uncertain"
            out.append(Edge(src, dst, t, LAYER_OF[EdgeType(t)].value, round(conf, 4), status, items))
        return out

    def neighbors(self, eid: str) -> list[Edge]:
        return self.edges("src=? OR dst=?", (eid, eid))

    def merge_entities(self, src: str, dst: str) -> None:
        """Merge entity ``src`` into ``dst``: repoint assertions and aliases, keep dst's label."""
        if src == dst:
            return
        a, b = self.entity(src), self.entity(dst)
        if not a or not b:
            raise KeyError("unknown entity")
        self.upsert_entity(dst, NodeType(b["type"]), b["label"], {**a["props"], **b["props"],
                           "merged_from": sorted(set((b["props"].get("merged_from") or []) + [src]))}, [a["label"]])
        self.db.execute("UPDATE assertions SET src=? WHERE src=?", (dst, src))
        self.db.execute("UPDATE assertions SET dst=? WHERE dst=?", (dst, src))
        self.db.execute("DELETE FROM assertions WHERE src=dst")
        self.db.execute("UPDATE OR IGNORE aliases SET entity_id=? WHERE entity_id=?", (dst, src))
        self.db.execute("DELETE FROM aliases WHERE entity_id=?", (src,))
        self.db.execute("DELETE FROM entities WHERE id=?", (src,))
        self.db.execute("INSERT OR REPLACE INTO merges(src, dst, merged_at) VALUES (?,?,?)", (src, dst, now_iso()))

    def reject_assertion(self, aid: str, reason: str) -> None:
        row = self.db.execute("SELECT * FROM assertions WHERE id=?", (aid,)).fetchone()
        if not row:
            raise KeyError(aid)
        self.db.execute("INSERT OR REPLACE INTO rejections(src, dst, type, evidence_id, reason, rejected_at) VALUES (?,?,?,?,?,?)",
                        (row["src"], row["dst"], row["type"], row["evidence_id"], reason, now_iso()))
        self.db.execute("DELETE FROM assertions WHERE id=?", (aid,))

    def apply_curation(self) -> None:
        """Re-apply analyst merges and rejections after a rebuild."""
        for m in self.db.execute("SELECT src, dst FROM merges ORDER BY merged_at").fetchall():
            if self.entity(m["src"]) and self.entity(m["dst"]):
                self.merge_entities(m["src"], m["dst"])
        self.db.execute("""DELETE FROM assertions WHERE EXISTS (SELECT 1 FROM rejections r WHERE r.src=assertions.src
                           AND r.dst=assertions.dst AND r.type=assertions.type
                           AND COALESCE(r.evidence_id,'')=COALESCE(assertions.evidence_id,''))""")

    def commit(self) -> None:
        self.db.commit()

    def stats(self) -> dict:
        q = lambda sql: self.db.execute(sql).fetchall()
        return {
            "entities": {r[0]: r[1] for r in q("SELECT type, COUNT(*) FROM entities GROUP BY type")},
            "assertions": {r[0]: r[1] for r in q("SELECT type, COUNT(*) FROM assertions GROUP BY type")},
            "evidence": {r[0]: r[1] for r in q("SELECT basis, COUNT(*) FROM evidence GROUP BY basis")},
            "raw_documents": {r[0]: r[1] for r in q("SELECT collector, COUNT(*) FROM raw_documents GROUP BY collector")},
        }
