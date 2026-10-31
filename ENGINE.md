# How Enterprise Atlas works

This is the deep dive behind the decision map: how the ontology is defined, how evidence becomes claims and
claims become a graph, and how the engine reasons from *where people sit* and *what they publicly work on*
to *who matters for a deal*. Every number below is taken from the code (`engine/atlas/`) or from the live
Mercedes-Benz build (31 Oct 2026).

The same content runs live on your data in the UI's **How it works** view.

---

## 0. The pipeline at a glance

```
collectors ──▶ raw_documents ──▶ evidence ──▶ entities + aliases ──▶ assertions ──▶ edges ──▶ read models
(Needle,        (verbatim JSON,   (URL +        (typed nodes,          (one claim,     (aggregated   (decision map,
 web, TED)       never deleted)    locator +     resolved by name)      one source,     per type,     buying center,
                                   basis)                               one date)       capped)       entry paths)
```

| Stage | Mercedes-Benz build |
|---|---|
| Raw documents | 26 (14 Needle people searches, 12 web records) |
| Evidence items | 111 |
| Entities | 154 (88 people, 13 business units, 15 functions, 18 teams, …) |
| Assertions | 377 |

**Design decision: the graph is a deterministic replay.**
- `atlas build` deletes every *derived* assertion and replays all raw documents through the current parsers.
- Improving a rule (say, adding "Global Customer Service & Parts" as an after-sales name) upgrades every past
  harvest, without spending a single new LinkedIn search.
- Analyst curation (merges, rejections, manual claims) is stored separately and re-applied after each rebuild
  (`Store.apply_curation`).

---

## 1. The ontology: two graphs in one store

`engine/atlas/ontology.py`

### Node types (12)

`Company · BusinessUnit · Function · Team · Person · Role · Project · Technology · Partner · Event · Tender · Topic`

- **Topic** is the problem being sold into, here "Warranty & after-sales analytics". Buying-center edges point
  at the Topic. That makes the buying center *problem-relative*: the same person can sponsor one problem and be
  irrelevant to another.
- **Function** and **Team** are created on the fly from headlines and job ads, scoped to a unit. For example,
  `fn:mb-ag:after_sales` and `team:mb-ag:after_sales_data` are different nodes from `fn:mb-vans:after_sales`.

### Relationship types (22), grouped into three layers

| Layer | Edge types |
|---|---|
| **Organization**: who belongs where | `BELONGS_TO`, `WORKS_IN`, `HOLDS_ROLE`, `REPORTS_TO` |
| **Buying center**: who matters for this problem | `OWNS_PROBLEM`, `OWNS_PROJECT`, `SPONSORS`, `EVALUATES`, `APPROVES_INTEGRATION`, `CONTROLS_PROCUREMENT`, `INFLUENCES`, `INTRODUCES_TO`, `SPOKE_ABOUT`, `WORKS_ON`, `HIRING_FOR` |
| **Ecosystem**: what surrounds the account | `SPOKE_AT`, `CONTRIBUTED_TO`, `USES_TECH`, `PARTNERS_WITH`, `PROCURED`, `AWARDED_TO`, `MEMBER_OF` |

The two graphs overlap but are not the same. Purchasing influence does not follow the reporting line.
Example from the build: the team that would evaluate an after-sales analytics tool sits in **IT After-Sales**,
not in the after-sales business function (see §7).

### Storage model

`engine/atlas/store.py`, SQLite:

| Table | Holds |
|---|---|
| `raw_documents` | Every collector response, verbatim, with request and timestamp |
| `evidence` | A citable unit: URL, locator, title, excerpt, **basis**, provider, access (public/licensed), observed/published date |
| `entities` | Typed nodes with JSON properties |
| `aliases` | Normalized names → entity (used for resolution; "Jörg" = "Joerg" = "Jorg") |
| `assertions` | One claim: `src –type→ dst`, basis, confidence, status, evidence id, observed date, extractor, rationale |
| `merges`, `rejections` | Analyst curation, re-applied after rebuilds |

Edges are never stored. They are computed from assertions on read, so corroboration and contradiction stay
visible: you can always see the individual claims behind a line.

---

## 2. Provenance: every claim has a basis, every basis has a ceiling

### Basis ceilings and what each basis may establish

Every assertion has a **basis**: the kind of observation that supports it. Each basis has a confidence
ceiling and a whitelist of relationships it is allowed to establish.

| Basis | Ceiling | May establish |
|---|---|---|
| Official company page / report | 0.95 | BELONGS_TO, WORKS_IN, HOLDS_ROLE, OWNS_PROJECT, CONTROLS_PROCUREMENT, USES_TECH, PARTNERS_WITH, REPORTS_TO |
| Procurement record (TED, OCDS) | 0.95 | PROCURED, AWARDED_TO, CONTROLS_PROCUREMENT, OWNS_PROJECT, USES_TECH |
| Event programme | 0.90 | SPOKE_AT, SPOKE_ABOUT, WORKS_IN, HOLDS_ROLE |
| LinkedIn profile (self-reported) | 0.85 | WORKS_IN, HOLDS_ROLE, WORKS_ON |
| Association / working group | 0.85 | MEMBER_OF, CONTRIBUTED_TO |
| Publication / patent / OSS | 0.85 | CONTRIBUTED_TO, WORKS_ON, USES_TECH |
| Job ad | 0.80 | HIRING_FOR, USES_TECH, BELONGS_TO |
| Press | 0.75 | PARTNERS_WITH, USES_TECH, OWNS_PROJECT, HOLDS_ROLE |
| Vendor claim (case study) | 0.70 | CONTRIBUTED_TO, USES_TECH, PARTNERS_WITH |
| Engine heuristic | 0.60 | nothing; always "inferred" |
| Analyst | 1.00 | anything |

### Rules applied when a claim is written

`clamp_confidence`:

```
heuristic basis            → min(c, 0.60), status "inferred"
edge type not whitelisted  → min(c, 0.45), status "uncertain"
otherwise                  → min(c, ceiling), "confirmed" if ≥ 0.70 else "inferred"
```

So a conference talk can never prove that the speaker owns the budget. If anyone, human or LLM extractor, writes
`OWNS_PROJECT` from an event programme, it lands at ≤ 0.45 and "uncertain". This is enforced in the store, not
in a prompt.

### Rules applied when claims are aggregated into an edge

`Store.edges`:

```
one vote per source URL       (the same profile returned by three searches is still one source)
edge confidence = noisy-OR    1 − Π (1 − cᵢ)
if any claim is confirmed     → confirmed
if only heuristic claims      → min(noisy-OR, 0.60), inferred
if only weak claims           → min(noisy-OR, 0.45 + 0.08·(n − 1), 0.80); inferred once n ≥ 3, else uncertain
```

### Live example: corroboration

`After-Sales —BELONGS_TO→ Mercedes-Benz AG`.
- 27 employee headlines place the after-sales function in Mercedes-Benz AG.
- Each headline alone is weak (0.35, because a self-reported headline isn't allowed to prove org structure).
- Together they lift the edge to **0.80, "inferred"**. It stays below "confirmed" until an official source says so.

A single sourced annual-report line would beat all 27 headlines.

---

## 3. Placement: headlines become org structure

`engine/atlas/titles.py` and `engine/atlas/build.py → build_needle_people`

Each LinkedIn hit has a self-reported headline. The parser turns it into structure in six steps.

1. **Split the employer.** Each `|` segment is checked for ` at `, ` bei `, ` @ ` or ` chez `. The part after the
   marker is the employer hint; the rest is the title.
   - `"Service Associate | invoice & warranty bei Mercedes-Benz AG"` → title `Service Associate | invoice & warranty`, employer `Mercedes-Benz AG`.
2. **Normalize.** Lowercase, fold umlauts (ä→ae, ö→oe, ü→ue, ß→ss), and turn punctuation into spaces.
   - `Qualität` becomes `qualitaet`, so English and German lexicons both match.
3. **Seniority ladder** (first match wins, matched on the title only):
   `intern` → `assistant` → `board` → `vp` → `director` (Director, Head of, Leiter, Leitung, Abteilungsleiter) →
   `manager` (Team Lead, Teamleiter, Manager, Product Owner, Projektleiter) →
   `ic` (Specialist, Engineer, Analyst, Referent, Sachbearbeiter, Architect, Controller…).
4. **Functions (13) and sub-teams (8)** from EN/DE lexicons.
   - Functions: after-sales, warranty, quality, data & AI, IT, procurement, sales & marketing, finance, R&D,
     production, strategy, HR, legal.
   - After-sales also matches `Kundendienst`, `Service & Parts` and `Global Customer Service & Parts`.
   - Warranty also matches `Gewährleistung`, `Garantie`, `Kulanz` and `Goodwill`.
   - Sub-teams: warranty, parts, technical after-sales, digital after-sales, after-sales data/AI, field quality,
     IT procurement, enterprise architecture.
   - The most specific domain wins as the primary function. Warranty and procurement beat quality and
     after-sales, which beat IT, which beats generic data/AI.
5. **Business unit** from the target's lexicon (`targets/mercedes.py`): Cars, Vans, MB.OS, AMG, Mobility, MBUSA,
   R&D North America and India, national sales companies (`Mercedes-Benz Schweiz AG`…), Daimler Truck.
   - Searches are scoped to the Mercedes-Benz AG LinkedIn company, so the default unit is Mercedes-Benz AG.
6. **Topics** for the problem: warranty, after-sales, field quality, analytics.

### Placement into the graph

```
unit ──BELONGS_TO── fn:<unit>:<function> ──BELONGS_TO── team:<unit>:<subteam> ──WORKS_IN── person
       (profile basis, 0.35 each;           (0.35 each)                         (0.75, or 0.50 if a hygiene
        corroboration lifts it)                                                 note applies)
```

### Worked example

`"Director of Service & Parts Business and Warranty & Goodwill Mercedes-Benz Cars bei Mercedes-Benz AG"`

| Field | Value |
|---|---|
| employer | Mercedes-Benz AG |
| seniority | `director` |
| functions | after_sales, warranty |
| sub-teams | warranty, parts |
| unit | Mercedes-Benz Cars |
| topics | warranty, after_sales |
| placement | Person → `team:mb-cars:warranty` → `fn:mb-cars:after_sales` → Mercedes-Benz Cars → Mercedes-Benz AG |
| roles | business sponsor 0.55, problem owner 0.45 (see §5) |

---

## 4. Hygiene: cleaning what LinkedIn gets wrong

| Rule | Trigger | Effect |
|---|---|---|
| **Stale: spin-off** | Title mentions trucks, buses, EvoBus, Fuso, Freightliner | Placed under **Daimler Truck** (separate company since 2021), with a note; WORKS_IN confidence drops to 0.50 |
| **Stale: old name** | Employer is "Daimler AG" (pre-2022 name) | Note "affiliation may be stale", confidence 0.50 |
| **Alumni** | Company-scoped search, but the headline names a different employer (e.g. *"Digital Transformation Lead at Hitachi Energy"*) | Not placed inside Mercedes. Becomes WORKS_IN at the new employer, plus an **introducer** hypothesis (0.30): alumni know the current team |
| **Partner** | Headline says *"… to / for Mercedes-Benz"*, *"on behalf of"*, freelance or contractor | Becomes a Partner node with PARTNERS_WITH the company (0.40), plus introducer 0.45 and champion 0.30 if in the domain |
| **Anonymous twin** | The same member is named in one search and "LinkedIn Member" in another (visibility depends on the query) | Identical normalized headline and location, with exactly one named candidate → merged automatically. 2 merges in the build (e.g. *"Warranty & Goodwill Controlling Vans"*) |
| **Same source, many searches** | One profile returned by several title searches | Counted once per URL in edges and in the evidence score |

---

## 5. Buying roles: domain plus seniority, never seniority alone

`engine/atlas/buying.py → infer_roles`

Roles are **hypotheses**. They are stored with basis `heuristic`, so they are capped at 0.60 and always marked
"inferred". Every role carries a rationale string that names the signals that fired.

The problem definition (`problems.py`) declares the **owning functions** (after-sales, warranty, quality) and
**owning sub-teams** (warranty, after-sales data, field quality, technical after-sales, digital after-sales).

| Signal | Role | Confidence |
|---|---|---|
| Director/VP inside an owning function (not procurement) | **business sponsor** + problem owner | 0.50 (+0.05 in an owning sub-team) / 0.45 |
| Manager / team lead inside an owning function | **problem owner** | 0.50 (+0.08 in an owning sub-team); 0.40 for pure data roles |
| Individual contributor inside an owning function | **user** | 0.50 |
| Data/AI role embedded in the domain | **evaluator** | 0.58 (manager+) / 0.45 (IC) |
| Data/AI lead not linked to the domain, but title hits a topic | evaluator | 0.30 |
| IT title (IT, architect, platform, cloud, integration, SAP…), manager+ or any architect, not procurement | **technical approver** | 0.30 (+0.15 if serving the domain) |
| Procurement function | **procurement** | 0.35 (+0.15 for IT/software/indirect or domain categories) |
| Public talk or contribution on an on-problem topic (event, publication, association) | **champion** | 0.50 |
| Assistant to leadership in the domain | **introducer** | 0.35 |
| Partner on the account | introducer / champion | 0.45 / 0.30 |
| Alumni | introducer | 0.30 |
| Intern, working student, thesis | none | n/a |

What never happens:
- A VP of Marketing never becomes a sponsor for warranty analytics.
- A "Head of Supplier Management, Global Customer Service & Parts" is routed to **procurement**, not
  sponsorship, because the procurement function overrides domain sponsorship.

---

## 6. Ranking: an explainable score

`score_person`

```
score = 100 × ( 0.40 · problem fit
              + 0.30 · role strength
              + 0.15 · evidence
              + 0.15 · reachability )

problem fit    = min(1, 0.25·#topic hits + 0.35·[in owning sub-team] + 0.20·[in owning function])
role strength  = min(1, max over roles of role_weight × confidence / 0.6)
                 role_weight: sponsor 1.0 · owner 0.95 · evaluator 0.9 · champion 0.8 · introducer 0.55
                              technical approver 0.6 · procurement 0.5 · user 0.35
evidence       = min(1, 0.35 + 0.20·(independent sources − 1) + public-activity bonus)
reachability   = degree (1st 1.0 · 2nd 0.8 · 3rd+ 0.45 · out of network 0.3) × (named 1.0 · hidden 0.7)
```

The inspector drawer shows all four bars for every person.
- Example: the top sponsor candidate (Director, Service & Parts and Warranty & Goodwill, Mercedes-Benz Cars) ranks 85 (fit 100, role 92, evidence 35, reachability 80).
- His low evidence score is honest. All of it comes from one self-reported headline. A talk or an official
  mention would raise it.

### Entry paths

`report.entry_paths`

Each path picks real people, ranked by confidence × score, without reusing anyone within the path:

| Path | Steps |
|---|---|
| Bottom-up | evaluator → problem owner (preferring warranty/quality) → sponsor |
| Champion first | champion → evaluator → sponsor |
| Warm introduction | introducer (preferring assistants) → problem owner → sponsor |
| Formal vendor route | procurement (preferring software/IT categories) → technical approver (preferring after-sales) → sponsor |

---

## 7. The hidden-intelligence layer

`collectors/web.py`, `collectors/ted.py`, `extract.py`

LinkedIn tells you where people sit. Other public sources tell you what they work on, and they attach to the
**same nodes** the profiles created.

- **Fetched pages.** With network access and an `ANTHROPIC_API_KEY`, `harvest-web` fetches each page. Claude
  extracts typed entities and relations into a strict schema (`Extraction`), and every relation must carry a
  **verbatim quote**. The system prompt forbids authority claims from talks; the store's basis ceiling enforces
  that anyway.
- **Analyst records.** An analyst (or Claude in a session) can write the same `Extraction` structure by hand, and
  pin `id`s to existing teams or units so evidence lands on the right node.
- **Name resolution.** Person names are resolved against the LinkedIn harvest by normalized alias.
  The test suite checks that a speaker named on a conference page attaches to the LinkedIn person instead of
  creating a duplicate.
- **Champion detection.** Any person with SPOKE_ABOUT / CONTRIBUTED_TO / WORKS_ON pointing at an on-problem
  node gains a champion hypothesis (0.50) and a ranking bonus.

### Examples from the Mercedes-Benz build

| Source (basis) | What it added |
|---|---|
| Job ad: *Team Data, Analytics & AI* | `After-Sales Data, AI & Analytics —BELONGS_TO→ IT After-Sales`; `USES_TECH → Databricks, AWS`; `HIRING_FOR → Data mesh in After-Sales`. The evaluator sits in IT, not in the business. |
| 3 job ads (IT Aftersales data engineering intern, AI thesis, working student) | Confirm an **IT After-Sales** team inside IT & Architecture that is actively hiring for after-sales data and AI |
| Job ad: MBUSA *Sr. Analyst Customer Services BI* | A Customer Services BI team at Mercedes-Benz USA |
| Event programme: Data + AI Summit 2026 | Anil Gadam (MBUSA) drives AI/ML adoption across Sales, Marketing and Aftersales → **champion** |
| Event programme: Data + AI Summit 2025 | Alexander Summa (Mercedes-Benz Group): cross-cloud data mesh; Frankie Cancino (MB R&D NA) |
| Vendor claim: Qlik case study | Mercedes-Benz India after-sales BI on QlikView; Qlik as an existing vendor |
| Association: Catena-X Quality | Industry early-warning standard on field and warranty data (CX-0123), a relevant ecosystem lever |

`harvest-ted` adds EU tenders. Mercedes-Benz is private, so it appears mostly as a *supplier* there, which maps
its public-sector sales and service organization rather than its buying.

---

## 8. Curation and rebuild

From the inspector drawer, or the API:
- **Reject** a claim (`POST /api/assertions/{id}/reject`).
- **Merge** two entities (`POST /api/merge`).
- **Add** a relationship (`POST /api/assertions`). Non-analyst claims require a source URL.

All of these are stored outside the derived data and re-applied after every rebuild. A wrong inference can be
corrected once, and the correction survives every future harvest.

---

## 9. Known limits

- **LinkedIn through Needle on a standard account.**
  - About 100 people searches a day, 10 hits per page.
  - Out-of-network members return as "LinkedIn Member" with headline only; the engine keeps them as anonymous seats.
  - Sales Navigator raises the limits and adds department filters.
- **Lexical parsing.** Vague headlines ("Enthusiasm empowered people") place nobody. The fix is a profile fetch
  or an extra source, not a guess.
- **Hypotheses, not facts.** Roles are hypotheses for a human to validate. The UI says so on every role card,
  and the evidence drawer shows why.
