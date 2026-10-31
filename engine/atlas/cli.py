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


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="atlas")
    ap.add_argument("--db", default=DEFAULT_DB)
    ap.add_argument("--problem", default="warranty-aftersales-analytics", choices=list(PROBLEMS))
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("build")
    imp = sub.add_parser("import"); imp.add_argument("files", nargs="+")
    hn = sub.add_parser("harvest-needle"); hn.add_argument("--pages", type=int, default=3); hn.add_argument("--reserve", type=int, default=10)
    ht = sub.add_parser("harvest-ted"); ht.add_argument("--limit", type=int, default=50)
    hv = sub.add_parser("harvest-web"); hv.add_argument("urls", nargs="*")
    sub.add_parser("report")
    sub.add_parser("stats")
    ex = sub.add_parser("export"); ex.add_argument("out")
    es = sub.add_parser("export-site"); es.add_argument("out"); es.add_argument("--no-redact", action="store_true")
    a = ap.parse_args(argv)

    store = Store(a.db)
    problem = PROBLEMS[a.problem]

    if a.cmd == "import":
        from .collectors.needle import import_mcp_response
        n = 0
        for f in a.files:
            for line in Path(f).read_text().splitlines():
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
        print(f"imported {n} raw documents")
        print(json.dumps(rebuild(store, a.problem), indent=2))
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
