# Enterprise Atlas

Enterprise Atlas is a hackathon MVP for reconstructing the buying center around a specific enterprise problem. A researcher supplies a target company, a startup product description, and an optional geography. The app expands the problem into business-language synonyms, discovers public sources, extracts conservative structured facts, builds a typed Cytoscape.js graph, ranks stakeholder candidates, and finds evidence-backed entry routes.

The product is intentionally an evidence graph, not a scraped org chart. Every extracted relationship carries source references, an observed date, confidence, and one of three statuses: `confirmed`, `inferred`, or `uncertain`.

## What is implemented

- Product-to-problem synonym generation, with a deterministic fallback
- Live public-web discovery through a provider adapter (`Tavily` or `Brave Search`)
- Normal HTTP retrieval for public HTML and PDF handoff to the structured extractor
- OpenAI Responses API extraction with a strict entity/relationship JSON schema
- Conservative exact-context entity resolution that leaves ambiguous entities separate
- Typed graph nodes and edges matching the Enterprise Atlas ontology
- Stakeholder scoring from problem ownership, evidence strength, buying signal, and reachability
- Short-path search from partners, events, and supplier/tender processes into target functions
- Interactive Cytoscape.js graph with status filters and click-through evidence detail
- Ranked buying committee, entry paths, unknowns, query ledger, and JSON export
- Graceful empty-state results when a source, search provider, or model call is unavailable
- Device-local persistence of the most recent live result through `localStorage`
- Visibly labeled illustrative fixture for UI development

Enterprise Atlas never sends outreach. It does not scrape LinkedIn, bypass access restrictions, guess emails, or turn a title or conference appearance into purchasing authority.

## Environment variables

Copy `.env.example` to `.env.local` and configure:

| Variable | Required | Purpose |
| --- | --- | --- |
| `OPENAI_API_KEY` | For structured extraction | Generates problem synonyms and extracts facts with a strict JSON schema. |
| `OPENAI_MODEL` | No | Defaults to `gpt-5-mini`. Use a model that supports Responses API structured output. |
| `SEARCH_PROVIDER` | For live discovery | `tavily` or `brave`. If omitted, the app detects a configured provider key. |
| `TAVILY_API_KEY` | When using Tavily | Public-web search and optional cached page content. |
| `BRAVE_SEARCH_API_KEY` | When using Brave | Public-web search. Pages are then retrieved normally by the server. |

Keep all keys server-side. None of these variables should use a `NEXT_PUBLIC_` prefix.

## Setup

Requirements: Node.js 22.13 or newer.

```bash
npm install
cp .env.example .env.local
npm run dev
```

Open the local URL printed by the development server. Without keys, the complete illustrative fixture remains available and a live run returns explicit configuration warnings rather than fabricated research.

## Demo flow

1. Start on the Mercedes-Benz warranty analytics fixture. The banner identifies it as illustrative.
2. Click a node or relationship. The right panel changes to its source trail, status, confidence, and unknowns.
3. Toggle confirmed, inferred, and uncertain relationships in the left panel.
4. Click a ranked stakeholder or an entry-path step to focus it in the graph.
5. Enter a new company and product description, then select **Run research**.
6. Review warnings, the live provider label, research ledger, evidence coverage, and unavailable sources.
7. Use **Export graph** to download the complete evidence graph as JSON.

A useful live example is:

- Target enterprise: `Mercedes-Benz Group`
- Startup product: `Natural-language AI analytics for warranty and aftersales data`
- Geography: `Germany`

## Verification

```bash
npm run build
npm test
```

The test flow compiles the Cloudflare-compatible app, server-renders the workspace, verifies API input validation, and checks the evidence guardrails in the fixture and extraction pipeline.

## Architecture

```text
Research form
  → product synonym expansion
  → search-provider adapter
  → permitted HTML/PDF retrieval
  → OpenAI strict fact extraction
  → conservative entity resolution
  → graph + scoring + path search
  → Cytoscape workspace + evidence ledger
```

- `app/api/research/route.ts` — the end-to-end research endpoint
- `lib/search-providers.ts` — Tavily and Brave adapter implementations
- `lib/openai-extraction.ts` — synonym and fact extraction with structured output
- `lib/research-pipeline.ts` — query planning, retrieval, resolution, ranking, and path finding
- `lib/atlas-types.ts` — ontology and result contracts
- `lib/sample-graph.ts` — visibly illustrative UI fixture with real public source URLs
- `components/GraphView.tsx` — Cytoscape graph
- `components/AtlasApp.tsx` — interactive research workspace

## Evidence rules

- A `confirmed` extracted edge without an evidence reference is automatically downgraded to `uncertain`.
- AI-suggested organizational matches are merged only when type and normalized label match exactly. Ambiguous entities remain separate.
- Public appearances establish topic involvement, not budget ownership or supplier authority.
- Missing identity, mandate, reporting line, and authority are displayed as unknowns.
- Source failures preserve the search result and mark it unavailable; the app does not retry through restricted or unauthorized routes.
- PDFs are provided to the OpenAI extractor by public URL. HTML is retrieved with a descriptive user agent through ordinary HTTP access only.

## Persistence and deployment

The MVP keeps persistence deliberately simple: the default fixture is JSON-compatible TypeScript data, live results are stored on the current device, and every graph can be exported as JSON. There is no database or hidden contact store.

For a team deployment, the next incremental step is a single SQLite/D1 table for research runs and one for evidence documents. The current `ResearchGraph` contract can be stored without changing the UI.

## Needle and optional providers

[Needle MCP](https://needle.app/docs/mcp/introduction) can be added later as a licensed sponsor/contact-data adapter. It is not used as the public source-discovery engine in this MVP, and its LinkedIn capabilities must not be used for scraping or automatic outreach. A safe integration would remain server-side, require an authenticated licensed workspace, attach provider provenance to every record, and keep all outreach actions disabled.

TED public notices and other formal procurement feeds fit behind the same provider boundary. They are most useful for public-sector targets; their absence is not treated as evidence that a private enterprise has no buying activity.

## Current MVP limits

- Search quality depends on the configured provider and what the target publishes publicly.
- Source text extraction is intentionally lightweight; JavaScript-only pages may yield snippets instead of full text.
- No OCR is applied to scanned PDFs.
- The app surfaces candidates and paths for human validation; it does not claim an authoritative org chart.
- There is no automatic contact enrichment or messaging.
