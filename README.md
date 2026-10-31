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

## Use it as a Claude Code skill

```text
/plugin marketplace add nur-rfz/enterprise-atlas
/plugin install enterprise-atlas@enterprise-atlas
```

Then ask Claude something like *"map the buying center for warranty analytics at Mercedes-Benz"* or
*"who would buy procurement automation at Siemens?"*. The skill (`skills/enterprise-atlas/SKILL.md`) walks
Claude through the steps:
1. Write a target and a problem definition from official sources.
2. Harvest LinkedIn through Needle (REST, or the Needle MCP tools).
3. Add job ads, event programmes, vendor case studies, associations and tenders.
4. Build and curate the graph.
5. Publish a redacted snapshot.

## Live demo (GitHub Pages)

`docs/` holds the static UI. Its data file, `docs/snapshot.json`, is **not committed**, because it is built from
harvested personal data. To generate it locally:

```bash
skills/enterprise-atlas/scripts/atlas.sh export-site ../docs
```

The export reduces LinkedIn-only people to initials and removes their profile URLs. Review it before you
publish. To publish, commit the file deliberately (`git add -f docs/snapshot.json`), then set
Settings → Pages to `main` / `/docs`. You can also host the folder anywhere that serves static files.

The hackathon pitch is in [`PITCH.md`](PITCH.md).

## Layout

```
engine/atlas/
  ontology.py          node/edge types, bases, what each basis may establish, confidence ceilings
  store.py             SQLite: raw_documents → evidence → entities/aliases → assertions; merges & rejections
  titles.py            EN/DE headline parser: seniority, function, sub-team, unit, employer, external/alumni
  targets/             mercedes.py (worked example) + _template.json for any company (ATLAS_TARGET=<name>)
  problem_defs/        _template.json for new problems (auto-registered)
  problems.py          problem definitions (topics, owning functions, harvest queries)
  buying.py            buying-role hypotheses + explainable ranking (fit, role, evidence, reachability)
  build.py             replays raw Needle documents into the org graph + buying roles
  collectors/
    needle.py          budget-aware LinkedIn harvester (Needle REST) + importer for Needle MCP output
    web.py             fetch pages, run/replay Claude extraction, champion detection from public activity
    ted.py             TED EU notices + German OCDS exports (oeffentlichevergabe.de)
  extract.py           Claude structured extraction: page → typed claims with verbatim quotes
  report.py / api.py   read models (org tree, committee, entry paths, signals), FastAPI, curation endpoints
  export.py            static, redacted site export for GitHub Pages
web/                   UI (decision map, overview, buying center, entry paths, org map, graph, evidence, sources)
skills/enterprise-atlas/ Claude Code skill (SKILL.md + scripts/atlas.sh); .claude-plugin/ holds the plugin manifests
docs/                  published static snapshot
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

Short version:
1. Headlines become org placement.
2. Hygiene rules handle stale, alumni, partner and duplicate profiles.
3. Buying roles come from domain plus seniority, never seniority alone.
4. Job ads, events, vendor case studies, associations and tenders add the facts LinkedIn lacks.

**Full deep dive: [`ENGINE.md`](ENGINE.md)** covers the ontology, the store, basis ceilings and confidence
math, the parser, every role rule with its confidence, the ranking formula, entry paths, and the
hidden-intelligence layer, all with live Mercedes-Benz examples. The UI's *How it works* view shows the same
material computed from your data.

## Present it

```bash
skills/enterprise-atlas/scripts/atlas.sh import ../data/needle/*.jsonl ../data/web/*.jsonl
skills/enterprise-atlas/scripts/atlas.sh serve        # http://localhost:8787
```

For a static build with real names, for private presentation only, run
`atlas.sh export-site /tmp/atlas-site --no-redact`, then serve it with `python3 -m http.server -d /tmp/atlas-site`.

## Data limits to know

* **Needle on a standard LinkedIn account.** About 100 people searches a day and 500 a week, 10 hits per page.
  Out-of-network members come back as "LinkedIn Member" with their headline only. The engine keeps them as
  anonymous seats, which still map the org. Sales Navigator on the connected account raises limits and adds
  department filters (`NEEDLE_MODE=sales_navigator`).
* **TED.** Mercedes-Benz is private, so it mostly appears in TED as a *supplier* (fleet and service contracts),
  not as a buyer.
* **The web records in `data/web/` are built from search-result summaries.** They are marked non-verbatim until the
  page is fetched and re-extracted with `harvest-web`.
