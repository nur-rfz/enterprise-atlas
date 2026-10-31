"""Enterprise Atlas command line.

    python -m atlas.cli build                    # seed + replay all raw documents
    python -m atlas.cli import ../data/needle/*.jsonl
    python -m atlas.cli harvest-needle --pages 3 # live LinkedIn harvest through Needle REST
    python -m atlas.cli harvest-ted              # EU procurement notices
    python -m atlas.cli report                   # org tree + buying committee
    python -m atlas.cli export graph.json
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from . import build as B
from .problems import PROBLEMS
from .report import buying_committee, graph_json, org_tree, print_tree, ranked_people
from .store import Store
from .targets import TARGET as T

DEFAULT_DB = os.environ.get("ATLAS_DB", str(Path(__file__).resolve().parents[2] / "data" / "atlas.sqlite"))


def rebuild(store: Store, problem_id: str) -> dict:
    from .builders import build_all
    return build_all(store, PROBLEMS[problem_id])


def print_context(problem) -> None:
    """The ontology context pack: what Claude reasons with when it runs the skill."""
    from .ontology import ESTABLISHES, LAYER_OF, MAX_CONFIDENCE_BY_BASIS, Basis, EdgeType, Layer, NodeType
    from .titles import FUNCTIONS, SUBFUNCTIONS
    print(f"# Atlas context pack · {T.COMPANY_NAME} · {problem.label}\n")
    print("## Ontology")
    print("Node types: " + ", ".join(n.value for n in NodeType))
    for layer in Layer:
        print(f"- {layer.value}: " + ", ".join(e.value for e in EdgeType if LAYER_OF[e] == layer))
    print("\n## Provenance rules (basis → ceiling → may establish)")
    for b in Basis:
        est = "anything" if b == Basis.ANALYST else (", ".join(sorted(e.value for e in ESTABLISHES[b])) or "hypotheses only")
        print(f"- {b.value:<22} {MAX_CONFIDENCE_BY_BASIS[b]:.2f}  {est}")
    print("- anything else → capped at 0.45, status uncertain")
    print("\n## Problem")
    print(f"{problem.description}")
    print(f"- owning functions: {', '.join(sorted(problem.owner_functions))} · owning sub-teams: {', '.join(sorted(problem.owner_subfunctions))}")
    print(f"- topics: " + "; ".join(f"{k}: {', '.join(v[:4])}" for k, v in problem.topics.items()))
    print(f"- LinkedIn title searches: {', '.join(problem.search_titles)}")
    print("\n## Buying-role rules (domain + seniority, never seniority alone)")
    for line in ["director+ in owning function → business sponsor 0.50–0.55 + problem owner 0.45",
                 "manager in owning function → problem owner 0.50–0.58", "IC in owning function → user 0.50",
                 "data/AI role in domain → evaluator 0.45–0.58", "IT architect / IT lead → technical approver 0.30–0.45",
                 "procurement → procurement 0.35–0.50", "public talk on topic → champion 0.50",
                 "assistant / partner / alumni → introducer 0.30–0.45"]:
        print(f"- {line}")
    print("\n## Target")
    print(f"- {T.COMPANY_NAME} ({T.COMPANY_ID}); LinkedIn company ids: {', '.join(T.LINKEDIN_COMPANIES.values()) or '-'}")
    for child, parent, src, conf in T.STRUCTURE:
        print(f"- {child} —BELONGS_TO→ {parent}  [{T.SOURCES[src]['basis']} · {src} · {conf}]")
    for entry in T.BOARD:
        print(f"- person: {entry[0]} — {entry[1]}  [{entry[2] if len(entry) > 2 else 'linkedin_company'}]")
    print(f"- functions known to the parser: {', '.join(FUNCTIONS)}; sub-teams: {', '.join(SUBFUNCTIONS)}")


def print_summary(store: Store, problem, people_before: int | None = None) -> None:
    """Compact, demo-friendly summary: graph size and the best candidate per buying role."""
    st = store.stats()
    people = st["entities"].get("Person", 0)
    delta = f"  (+{people - people_before} new)" if people_before is not None and people > people_before else ""
    print(f"\n{T.COMPANY_NAME} · {problem.label}")
    print(f"  people {people}{delta} · teams {st['entities'].get('Team', 0) + st['entities'].get('Function', 0)} · "
          f"claims {sum(st['assertions'].values())} · evidence {sum(st['evidence'].values())}")
    c = buying_committee(store, problem, limit_per_role=25)
    used: set[str] = set()
    for role in ("business_sponsor", "problem_owner", "evaluator", "technical_approver", "procurement", "champion", "introducer"):
        top = sorted(c[role]["top"], key=lambda p: -(p["confidence"] * (p["score"] or 1)))
        import re
        for prefer in {"procurement": [r"software|saas", r"\bit\b"]}.get(role, []):
            hits = [p for p in top if re.search(prefer, p.get("title") or "", re.I)]
            if hits:
                top = hits
                break
        top = [p for p in top if p["id"] not in used] or top  # one person per role where possible
        if top:
            p = top[0]
            used.add(p["id"])
            name = p["label"] if p.get("name_visible") is not False else f"[name hidden] {p['title']}"
            print(f"  {role.replace('_', ' '):<19} {name[:48]:<48} {int(p['confidence'] * 100):>3}%  rank {p['score']}")


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="atlas")
    ap.add_argument("--db", default=DEFAULT_DB)
    ap.add_argument("--problem", default=os.environ.get("ATLAS_PROBLEM", "warranty-aftersales-analytics"), choices=list(PROBLEMS))
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("build")
    imp = sub.add_parser("import"); imp.add_argument("files", nargs="+")
    hn = sub.add_parser("harvest-needle"); hn.add_argument("--pages", type=int, default=3); hn.add_argument("--reserve", type=int, default=10)
    ht = sub.add_parser("harvest-ted"); ht.add_argument("--limit", type=int, default=50)
    hv = sub.add_parser("harvest-web"); hv.add_argument("urls", nargs="*")
    sub.add_parser("report")
    sub.add_parser("summary")
    sub.add_parser("context")
    sub.add_parser("stats")
    ex = sub.add_parser("export"); ex.add_argument("out")
    es = sub.add_parser("export-site"); es.add_argument("out"); es.add_argument("--no-redact", action="store_true")
    a = ap.parse_args(argv)

    store = Store(a.db)
    problem = PROBLEMS[a.problem]

    if a.cmd == "import":
        from .collectors.needle import import_mcp_response
        n = 0
        files: list[Path] = []
        for f in a.files:
            p = Path(f)
            files += sorted(x for x in p.rglob("*") if x.suffix in (".jsonl", ".json")) if p.is_dir() else [p]
        for p in files:
            text = p.read_text().strip()
            if not text:
                continue
            if p.suffix == ".json":
                # a raw Needle MCP response saved as-is: {"hits": [...], ...}
                data = json.loads(text)
                if "hits" in data:
                    import_mcp_response(store, "people", data.get("label") or f"file:{p.stem}", data.get("params") or {}, data)
                    n += 1
                continue
            for line in text.splitlines():
                if line.strip():
                    rec = json.loads(line)
                    if rec.get("kind") in ("ted", "vergabe"):
                        store.put_raw("ted.search" if rec["kind"] == "ted" else "vergabe.ocds", rec["request"], rec["payload"])
                    elif rec.get("kind") in ("people", "jobs", "job", "profile", "company"):
                        import_mcp_response(store, rec["kind"], rec["label"], rec["params"], rec["payload"], rec.get("page", 0))
                    else:
                        from .collectors.web import import_web_record
                        import_web_record(store, rec)
                    n += 1
        store.commit()
        before = len(store.entities(__import__("atlas.ontology", fromlist=["NodeType"]).NodeType.PERSON))
        rebuild(store, a.problem)
        print(f"imported {n} raw documents from {len(files)} file(s)")
        print_summary(store, problem, before)
    elif a.cmd == "build":
        print(json.dumps(rebuild(store, a.problem), indent=2))
    elif a.cmd == "harvest-needle":
        from .collectors.needle import Budget, NeedleClient, harvest_people, plan_people_queries
        client = NeedleClient(budget=Budget(reserve_day=a.reserve))
        queries = plan_people_queries(problem, list(T.LINKEDIN_COMPANIES.values()), a.pages)
        print(json.dumps(harvest_people(store, client, queries), indent=2))
        print(json.dumps(rebuild(store, a.problem), indent=2))
    elif a.cmd == "harvest-ted":
        from .collectors.ted import harvest_ted
        print(json.dumps(harvest_ted(store, problem, limit=a.limit), indent=2))
        print(json.dumps(rebuild(store, a.problem), indent=2))
    elif a.cmd == "harvest-web":
        from .collectors.web import harvest_urls
        print(json.dumps(harvest_urls(store, a.urls), indent=2))
        print(json.dumps(rebuild(store, a.problem), indent=2))
    elif a.cmd == "context":
        print_context(problem)
    elif a.cmd == "summary":
        print_summary(store, problem)
    elif a.cmd == "stats":
        print(json.dumps(store.stats(), indent=2))
    elif a.cmd == "report":
        print("=== Organizational graph ===")
        print_tree(org_tree(store, T.COMPANY_ID))
        print("\n=== Buying center:", problem.label, "===")
        for role, block in buying_committee(store, problem).items():
            if not block["count"]:
                continue
            print(f"\n{role} ({block['count']})")
            for p in block["top"][:5]:
                print(f"  {p['score']:>3}  {p['label']}  — {p['title']}  [{p['unit']}]")
                print(f"       {p['rationale']}")
        print("\n=== Top 15 ===")
        for p in ranked_people(store, 15):
            print(f"  {p['score']:>3}  {p['label']}  {p['roles']}")
    elif a.cmd == "export-site":
        os.environ["ATLAS_DB"] = a.db
        from .export import export_site
        print(json.dumps(export_site(a.out, redact=not a.no_redact), indent=2))
    elif a.cmd == "export":
        Path(a.out).write_text(json.dumps(graph_json(store), indent=1, ensure_ascii=False, default=str))
        print(f"wrote {a.out}")


if __name__ == "__main__":
    main()
