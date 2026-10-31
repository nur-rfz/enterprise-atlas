# Enterprise Atlas

Maps **how decisions happen** inside a large enterprise, not just its reporting lines.
The first target is Mercedes-Benz, for a startup selling warranty and after-sales analytics.

Two overlapping graphs live in one store:

* **Organizational graph.** Company → business unit → function → team → person.
* **Buying-center graph.** Who owns the problem, who sponsors, who evaluates, who approves the integration,
  who runs procurement, who can introduce you. These are built per *problem*, because the same person can
  matter for one product and be irrelevant for another.

The key rule: **every relationship is an aggregation of sourced assertions.** Each assertion has a source,
an observation date, a confidence and a *basis* (LinkedIn profile, official company page, procurement record,
event programme, vendor claim, job ad, association, publication, press, engine heuristic, analyst).
Each basis can only establish certain relationships. A conference talk proves `SPOKE_ABOUT`. It is capped
at "uncertain" if anything (human or LLM) tries to use it to claim `OWNS_PROJECT` or `CONTROLS_PROCUREMENT`.

## Layout

```
engine/atlas/
  ontology.py          node/edge types, bases, what each basis may establish, confidence ceilings
  store.py             SQLite: raw_documents → evidence → entities/aliases → assertions; merges & rejections
  titles.py            EN/DE headline parser: seniority, function, sub-team, unit, employer, external/alumni
  targets/mercedes.py  sourced seed structure, unit lexicon (Cars, Vans, MB.OS, MBUSA, Daimler Truck…), board
  problems.py          problem definitions (topics, owning functions, harvest queries)
  buying.py            buying-role hypotheses + explainable ranking (fit, role, evidence, reachability)
  build.py             replays raw Needle documents into the org graph + buying roles
  collectors/
    needle.py          budget-aware LinkedIn harvester (Needle REST) + importer for Needle MCP output
    web.py             fetch pages, run/replay Claude extraction, champion detection from public activity
    ted.py             TED EU notices + German OCDS exports (oeffentlichevergabe.de)
  extract.py           Claude structured extraction: page → typed claims with verbatim quotes
  report.py / api.py   read models, FastAPI, curation endpoints
web/                   UI (overview, buying center, org map, graph, evidence ledger, sources, inspector)
legacy/codex-mvp/      the previous TypeScript MVP, kept for reference
```

## Run

```bash
python3 -m venv .venv && .venv/bin/pip install -r engine/requirements.txt
cp .env.example .env   # add NEEDLE_API_KEY, NEEDLE_CONNECTED_ACCOUNT_ID, ANTHROPIC_API_KEY
cd engine
../.venv/bin/python -m atlas.cli import ../data/needle/*.jsonl ../data/web/*.jsonl   # load existing harvests
../.venv/bin/python -m atlas.cli harvest-needle --pages 3                           # live LinkedIn harvest
../.venv/bin/python -m atlas.cli harvest-ted                                         # EU tenders
../.venv/bin/python -m atlas.cli harvest-web https://…/speaker-page https://…/job-ad # pages → Claude → claims
../.venv/bin/python -m atlas.cli report
../.venv/bin/uvicorn atlas.api:app --port 8787                                       # UI at http://localhost:8787
../.venv/bin/python -m pytest -q tests
```

Raw responses are stored verbatim. `build` deterministically regenerates the graph from them, so a better
parser upgrades every past harvest. Analyst merges and claim rejections are stored separately and re-applied
after each rebuild.

## How the engine reasons

1. **Placement.** A headline like *"Director of Service & Parts Business and Warranty & Goodwill Mercedes-Benz Cars bei Mercedes-Benz AG"*
   becomes `seniority=director`, `function=after_sales`, `team=warranty`, `unit=Mercedes-Benz Cars`.
   Teams and functions are created on the fly. Their `BELONGS_TO` edges gain confidence as independent profiles corroborate them.
2. **Hygiene.**
   * "Daimler AG" employers and truck/bus titles are flagged as stale. Daimler Truck has been a separate company since 2021.
   * People whose headline names another employer are treated as **alumni**, an introduction route, not as Mercedes staff.
   * "…consultant to Mercedes-Benz" headlines become **partners**.
3. **Buying roles** come only from domain plus seniority, never seniority alone:
   * Director in warranty → sponsor *hypothesis*.
   * Data/AI lead embedded in after-sales → evaluator.
   * IT architect serving the domain → technical approver.
   * IT/software category manager → procurement.
   * Assistant to after-sales leadership → introducer.
   * Public talk on the topic → champion.
4. **Hidden-intelligence layer.** Job ads, event programmes, vendor case studies, associations and tenders
   add facts LinkedIn does not have. Example: a job ad places the *After-Sales Data, AI & Analytics* team inside
   *IT After-Sales* and names Databricks and AWS.

## Data limits to know

* **Needle on a standard LinkedIn account.** About 100 people searches a day and 500 a week, 10 hits per page.
  Out-of-network members come back as "LinkedIn Member" with their headline only. The engine keeps them as
  anonymous seats, which still map the org. Sales Navigator on the connected account raises limits and adds
  department filters (`NEEDLE_MODE=sales_navigator`).
* **TED.** Mercedes-Benz is private, so it mostly appears in TED as a *supplier* (fleet and service contracts),
  not as a buyer.
* **The web records in `data/web/` are built from search-result summaries.** They are marked non-verbatim until the
  page is fetched and re-extracted with `harvest-web`.
