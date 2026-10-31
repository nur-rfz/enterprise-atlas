---
name: enterprise-atlas
description: Build an evidence-backed buying-center map for a large enterprise account. Use when someone wants to know who decides, sponsors, evaluates, approves or procures a specific product inside a company (e.g. "who buys warranty analytics at Mercedes-Benz", "map the buying committee at Siemens for our procurement AI", "account map", "org chart for selling into X"). Harvests LinkedIn through Needle, adds job ads, event programmes, vendor case studies, associations and tenders, and produces an org graph, a per-problem buying-center graph, entry paths and a shareable UI. Every relationship carries a source, observation date and confidence.
---

# Enterprise Atlas

Maps **how decisions happen** inside an enterprise, not just its reporting lines. It builds two graphs in one store:

* **Organizational graph.** Company → business unit → function → team → person.
* **Buying-center graph, per problem.** Problem owner, business sponsor, evaluator, technical approver, procurement, champion, introducer and user.

The engine lives at the repository root of this plugin. Run every command through the wrapper script. It creates the virtualenv on first use:

```bash
SKILL_DIR="<base directory of this skill>"
"$SKILL_DIR/scripts/atlas.sh" report
```

## Non-negotiable rules

1. **Every relationship needs a source.** Use the claim types the engine provides. A talk proves `SPOKE_ABOUT`, never budget ownership. The store caps unsupported claims at "uncertain" anyway, so don't fight it.
2. **Seniority is not authority.** A sponsor hypothesis needs a problem-owning function, not just a big title.
3. **No guessing.**
   * Never invent names, emails or reporting lines.
   * LinkedIn "LinkedIn Member" results stay anonymous seats.
   * Paraphrased web evidence must say so in the record's `note`.
4. **No outreach.** This skill never sends LinkedIn messages, invitations or InMails, even though Needle exposes those tools.
5. **Privacy.**
   * Harvested data (`data/needle`, `data/web`, `data/atlas.sqlite`) is git-ignored. Keep it that way.
   * Publish only with `export-site`, which redacts LinkedIn-only people to initials by default.

## Workflow

### 1. Frame the target and the problem

Ask for two things if the user hasn't given them:
* the company;
* what the user sells, phrased as the enterprise problem it solves.

Then write two JSON files:

* **Target:** copy `engine/atlas/targets/_template.json` to `engine/atlas/targets/<slug>.json`.
  * Fill `UNITS`, `STRUCTURE`, `SOURCES` and `BOARD` only with facts an official source states (annual report, imprint, about page). Cite each one in `SOURCES`.
  * Get the LinkedIn company id with `needleGetLinkedinCompany`; the imprint in its description often lists the board.
  * Put units you can't source yet in `UNIT_PARENTS`. They become capped heuristic edges.
  * `UNIT_LEXICON` maps headline words to units, e.g. `"bu:acme-industrial": ["industrial"]`.
  * `EMPLOYER_PATTERNS` lists the strings that mean "works for the target".
* **Problem:** copy `engine/atlas/problem_defs/_template.json` to `engine/atlas/problem_defs/<id>.json`.
  * Set `topics` (EN plus local language), `owner_functions` and `owner_subfunctions`.
  * Add 10–20 `search_titles` covering owners, data leads, IT/architecture and procurement for that domain.

Select them for every command:

```bash
export ATLAS_TARGET=<slug>
"$SKILL_DIR/scripts/atlas.sh" --problem <id> build
```

The built-in example is `ATLAS_TARGET=mercedes` with the problem `warranty-aftersales-analytics`.

### 2. Harvest LinkedIn (Needle)

Needle setup: https://needle.app/agent-onboarding/SKILL.md.

* **Budget:** a standard LinkedIn account gets about 100 people searches a day and 500 a week, 10 hits per page.
* **Plan before searching:** one query per `search_titles` entry, scoped to the company id. Check `remainingUsage` after every call.

**Option A: REST (preferred when `NEEDLE_API_KEY` is set and `needle.app` is reachable).**

```bash
"$SKILL_DIR/scripts/atlas.sh" harvest-needle --pages 2 --reserve 10
```

**Option B: the Needle MCP tools.** Use this when the REST path is blocked.
1. Call `needleSearchLinkedinPeopleClassic` with `companies: ["<id>"]` and `advancedKeywords: {"title": "<keyword>"}`.
2. Pagination needs the same filters plus `cursor`.
3. Append one line per response to `data/needle/<date>.jsonl`:

```json
{"kind":"people","label":"title:<keyword>","page":0,"params":{...the call's filters...},"payload":{"hits":[{"publicIdentifier":..,"profileUrl":..,"fullName":..,"headline":..,"location":..,"degree":..}],"remainingUsage":{..}}}
```

Drop the `imageUrl*` fields to keep files small. Then import:

```bash
"$SKILL_DIR/scripts/atlas.sh" import ../data/needle/*.jsonl
```

### 3. Add the hidden-intelligence layer

LinkedIn tells you *where* people sit. These sources tell you *what they work on*. Search for each:

| Source | What to look for | Basis |
|---|---|---|
| Company careers / job boards | vacancies in the target unit naming platforms, projects, team names | `job_ad` |
| Conference programmes, speaker pages | employees speaking about the exact problem | `event_program` |
| Vendor / SI case studies | platform, partner, sometimes the client-side lead | `vendor_claim` |
| Associations, standards bodies | working groups, named contributors | `association` |
| TED / national tenders | buyer, winner, value, contact | `procurement_record` |
| Papers, patents, GitHub | technical champions | `publication` |

For each page, choose one of two routes:
* **With `ANTHROPIC_API_KEY` and network access:** run `atlas.sh harvest-web <url> …`. It fetches the page and extracts claims, each with a verbatim quote.
* **Otherwise:** write a record to `data/web/<date>.jsonl` with the extraction attached, then run `atlas.sh import`:

```json
{"kind":"web","url":"…","title":"…","basis":"job_ad","provider":"web search","observed_at":"YYYY-MM-DD",
 "note":"Excerpt is a search summary (not verbatim)",
 "extracted":{"basis":"job_ad","entities":[{"key":"t","type":"Team","name":"After-Sales Data, AI & Analytics","id":"team:mb-ag:after_sales_data"},
   {"key":"db","type":"Technology","name":"Databricks"}],
  "relations":[{"source_key":"t","target_key":"db","type":"USES_TECH","confidence":0.7,"quote":"…"}]}}
```

In these records:
* Pin `id` to an existing entity (team, unit or person) when you know it, so evidence attaches to the org graph instead of creating duplicates.
* Person names are resolved automatically against the LinkedIn harvest.

TED: `atlas.sh harvest-ted`. Private companies mostly appear there as *suppliers*.

### 4. Build, review and curate

```bash
"$SKILL_DIR/scripts/atlas.sh" build
"$SKILL_DIR/scripts/atlas.sh" report   # org tree, buying committee by role, top 15
"$SKILL_DIR/scripts/atlas.sh" serve    # UI at http://localhost:8787
```

Before presenting anything, read the report critically:
* **Former employees:** people whose headline names another employer become alumni (an introduction route).
* **Stale affiliations:** "Daimler AG"-style employers are flagged.
* **Duplicates:** anonymous duplicates of named people are merged automatically.
* **Wrong claims:** fix them with the UI's *Reject*, *Merge into…* and *Add relationship* actions, or the `/api/assertions`, `/api/merge` and `/api/assertions/{id}/reject` endpoints. Curation survives rebuilds.

### 5. Deliver

Summarize for the user:
* the top candidate per buying role, with the evidence behind each;
* the four entry paths from `GET /api/paths`;
* the hidden signals;
* what is still unknown.

To share, run `atlas.sh export-site ../docs`. It produces a static, redacted site; serve it with GitHub Pages from `/docs`.

## Files

* `engine/atlas/ontology.py`: node and edge types, bases, what each basis may establish.
* `engine/atlas/titles.py`: EN/DE headline parser. Extend its `FUNCTIONS` and `SUBFUNCTIONS` for new domains.
* `engine/atlas/buying.py`: role rules and ranking.
* `engine/atlas/collectors/`: `needle.py`, `web.py` (Claude extraction), `ted.py`.
* `web/`: the UI.
* `docs/`: the published snapshot.
