"""Static site export: the full UI plus a JSON snapshot, hostable on GitHub Pages.

By default people known only from licensed LinkedIn data are redacted to initials and
their profile URLs removed. People named on official pages, event programmes or press keep
their names. Use ``--no-redact`` only for private deployments.
"""
from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

from fastapi.testclient import TestClient

from .ontology import NodeType
from .store import Store

PUBLIC_BASES = {"official_company", "event_program", "press", "publication", "association", "procurement_record"}
WEB = Path(__file__).resolve().parents[2] / "web"


def _redactions(store: Store) -> dict[str, str]:
    """Return {original string -> replacement} for names, ids and profile URLs."""
    out: dict[str, str] = {}
    for p in store.entities(NodeType.PERSON):
        props = p["props"]
        if not props.get("profile_url") and not props.get("public_identifier"):
            continue  # not from LinkedIn
        basis = {e["basis"] for e in store.evidence(
            [a["evidence_id"] for a in store.assertions("src=? AND evidence_id IS NOT NULL", (p["id"],))])}
        if basis & PUBLIC_BASES:
            continue  # publicly named elsewhere
        new_id = "person:r:" + hashlib.sha1(p["id"].encode()).hexdigest()[:10]
        out[p["id"]] = new_id
        if props.get("name_visible"):
            parts = [w for w in p["label"].replace("Dr.", "").split() if w]
            initials = " ".join(w[0] + "." for w in parts[:3])
            out[p["label"]] = f"{initials} (name withheld)"
        if props.get("profile_url"):
            out[props["profile_url"]] = "https://www.linkedin.com/"
        if props.get("public_identifier"):
            out[props["public_identifier"]] = new_id.split(":")[-1]
    return out


def export_site(out_dir: str, redact: bool = True) -> dict:
    from .api import app, store

    client = TestClient(app)
    get = lambda p: client.get(p).json()
    snap = {p: get(p) for p in ("/api/meta", "/api/org", "/api/people", "/api/evidence", "/api/sources",
                                "/api/paths", "/api/signals", "/api/explain")}
    snap["/api/committee"] = get("/api/committee?limit=50")
    snap["/api/graph"] = get("/api/graph")
    s = store()
    ents = s.entities()
    snap["entities"] = {e["id"]: get(f"/api/entity/{e['id']}") for e in ents}
    snap["search"] = [{"id": e["id"], "type": e["type"], "label": e["label"], "headline": e["props"].get("headline")}
                      for e in ents]
    snap["/api/sources"]["configured"] = {"needle": False, "anthropic": False}
    from .store import now_iso
    snap["generated_at"] = now_iso()

    text = json.dumps(snap, ensure_ascii=False, default=str)
    n = 0
    if redact:
        for old, new in sorted(_redactions(s).items(), key=lambda kv: -len(kv[0])):
            if old and old in text:
                text = text.replace(json.dumps(old, ensure_ascii=False)[1:-1], json.dumps(new, ensure_ascii=False)[1:-1])
                n += 1
    if redact:
        import re
        text = re.sub(r"https?://(?:www\.)?linkedin\.com/in/[^\"\s]*", "https://www.linkedin.com/", text)
        text = re.sub(r"person:li:([^\"\s|]+)",
                      lambda m: "person:r:" + hashlib.sha1(("person:li:" + m.group(1)).encode()).hexdigest()[:10], text)
    out = Path(out_dir)
    if out.exists():
        shutil.rmtree(out)
    (out / "assets").mkdir(parents=True)
    for f in ("app.js", "style.css"):
        shutil.copy(WEB / f, out / "assets" / f)
    shutil.copytree(WEB / "vendor", out / "assets" / "vendor")
    html = (WEB / "index.html").read_text().replace("<head>", "<head>\n  <script>window.ATLAS_STATIC = true;</script>", 1)
    (out / "index.html").write_text(html)
    (out / "snapshot.json").write_text(text)
    (out / ".nojekyll").write_text("")
    return {"out": str(out), "entities": len(ents), "redactions": n, "bytes": len(text)}
