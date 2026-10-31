import {
  EDGE_TYPES,
  NODE_TYPES,
  type AtlasEdge,
  type AtlasEvidence,
  type AtlasNode,
  type EntryPath,
  type ExtractedFactSet,
  type ResearchGraph,
  type ResearchRequest,
  type SearchResult,
  type StakeholderCandidate,
} from "./atlas-types";
import { expandProductTerms, extractFacts } from "./openai-extraction";
import { getSearchProvider } from "./search-providers";

function slug(value: string) {
  return value.toLowerCase().normalize("NFKD").replace(/[^a-z0-9]+/g, "-").replace(/(^-|-$)/g, "").slice(0, 70) || "entity";
}

function decodeHtml(text: string) {
  return text.replace(/&nbsp;/gi, " ").replace(/&amp;/gi, "&").replace(/&quot;/gi, '"').replace(/&#39;/g, "'").replace(/&lt;/gi, "<").replace(/&gt;/gi, ">");
}

function htmlToText(html: string) {
  return decodeHtml(html
    .replace(/<script[\s\S]*?<\/script>/gi, " ")
    .replace(/<style[\s\S]*?<\/style>/gi, " ")
    .replace(/<noscript[\s\S]*?<\/noscript>/gi, " ")
    .replace(/<[^>]+>/g, " ")
    .replace(/\s+/g, " ")
    .trim()).slice(0, 18_000);
}

function buildQueries(company: string, terms: string[], geography?: string) {
  const quoted = `"${company}"`;
  const geo = geography ? ` ${geography}` : "";
  const top = terms.slice(0, 5);
  return [...new Set([
    ...top.map((term) => `${quoted} "${term}"${geo}`),
    `${quoted} (${top.slice(0, 3).map((term) => `"${term}"`).join(" OR ")}) conference OR webinar OR presentation`,
    `${quoted} (${top.slice(0, 3).map((term) => `"${term}"`).join(" OR ")}) partner OR case study`,
    `${quoted} (${top.slice(0, 3).map((term) => `"${term}"`).join(" OR ")}) jobs OR careers`,
    `${quoted} supplier portal procurement`,
  ])].slice(0, 9);
}

async function retrieve(result: SearchResult): Promise<SearchResult & { retrievedText: string; available: boolean; locator?: string }> {
  if (result.rawContent) return { ...result, retrievedText: result.rawContent.slice(0, 18_000), available: true, locator: "Search provider cached content" };
  if (/\.pdf($|\?)/i.test(result.url)) {
    return { ...result, retrievedText: result.snippet, available: true, locator: "PDF supplied to structured extractor by URL" };
  }
  try {
    const response = await fetch(result.url, {
      headers: { "user-agent": "EnterpriseAtlas/0.1 (+public research; respects access controls)", Accept: "text/html,application/xhtml+xml" },
      redirect: "follow",
      signal: AbortSignal.timeout(12_000),
    });
    if (!response.ok) return { ...result, retrievedText: result.snippet, available: false, locator: `Unavailable (${response.status})` };
    const contentType = response.headers.get("content-type") ?? "";
    if (!contentType.includes("html") && !contentType.includes("text")) {
      return { ...result, retrievedText: result.snippet, available: false, locator: `Unsupported content type: ${contentType || "unknown"}` };
    }
    return { ...result, retrievedText: htmlToText(await response.text()), available: true, locator: "Retrieved page text" };
  } catch {
    return { ...result, retrievedText: result.snippet, available: false, locator: "Source retrieval failed; using search snippet" };
  }
}

function resolveFacts(company: string, facts: ExtractedFactSet | null, evidence: AtlasEvidence[]): { nodes: AtlasNode[]; edges: AtlasEdge[] } {
  const companyNode: AtlasNode = { id: "target-company", type: "Company", label: company, summary: "Target enterprise supplied by the researcher.", evidenceIds: [], layers: ["organization", "buying_center"] };
  if (!facts) return { nodes: [companyNode], edges: [] };

  const nodeTypes = new Set<string>(NODE_TYPES);
  const edgeTypes = new Set<string>(EDGE_TYPES);
  const keyToId = new Map<string, string>([["target-company", companyNode.id], [slug(company), companyNode.id]]);
  const resolved = new Map<string, AtlasNode>([[`${companyNode.type}:${slug(companyNode.label)}`, companyNode]]);

  for (const fact of facts.nodes) {
    if (!nodeTypes.has(fact.type) || !fact.label?.trim()) continue;
    const identity = `${fact.type}:${slug(fact.label)}`;
    const existing = resolved.get(identity);
    const evidenceIds = fact.evidenceIndexes.map((index) => evidence[index]?.id).filter(Boolean);
    if (existing) {
      existing.evidenceIds = [...new Set([...existing.evidenceIds, ...evidenceIds])];
      existing.aliases = [...new Set([...(existing.aliases ?? []), ...(fact.aliases ?? [])])];
      keyToId.set(fact.key, existing.id);
      continue;
    }
    const id = `${slug(fact.type)}-${slug(fact.label)}`;
    const node: AtlasNode = {
      id,
      type: fact.type,
      label: fact.label.trim(),
      summary: fact.summary || "No summary extracted.",
      evidenceIds,
      aliases: fact.aliases,
      unknowns: fact.unknowns,
      layers: fact.layers?.length ? fact.layers : ["Company", "BusinessUnit", "Function", "Person", "Role"].includes(fact.type) ? ["organization"] : ["buying_center"],
    };
    resolved.set(identity, node);
    keyToId.set(fact.key, id);
  }

  const edges: AtlasEdge[] = [];
  for (const [index, fact] of facts.edges.entries()) {
    const source = keyToId.get(fact.sourceKey);
    const target = keyToId.get(fact.targetKey);
    if (!source || !target || source === target || !edgeTypes.has(fact.type)) continue;
    const evidenceIds = fact.evidenceIndexes.map((item) => evidence[item]?.id).filter(Boolean);
    const status = fact.status === "confirmed" && evidenceIds.length === 0 ? "uncertain" : fact.status;
    edges.push({
      id: `edge-${index + 1}-${source}-${target}`,
      source,
      target,
      type: fact.type,
      status,
      confidence: Math.max(0, Math.min(1, fact.confidence)),
      evidenceIds,
      rationale: fact.rationale,
      layer: fact.layer ?? (["BELONGS_TO", "WORKS_IN", "REPORTS_TO"].includes(fact.type) ? "organization" : ["PARTNERS_WITH", "PROCURED"].includes(fact.type) ? "ecosystem" : "buying_center"),
    });
  }
  return { nodes: [...resolved.values()], edges };
}

function scoreStakeholders(nodes: AtlasNode[], edges: AtlasEdge[]): StakeholderCandidate[] {
  const candidates = nodes.filter((node) => node.type === "Person" || node.type === "Role");
  return candidates.map((node): StakeholderCandidate => {
    const related = edges.filter((edge) => edge.source === node.id || edge.target === node.id);
    const types = new Set(related.map((edge) => edge.type));
    const linkedIds = new Set(related.flatMap((edge) => [edge.source, edge.target]));
    const linkedNodes = nodes.filter((item) => linkedIds.has(item.id));
    const problemOwnership = types.has("OWNS_PROJECT") || types.has("SPONSORS_PROJECT") ? 92 : types.has("EVALUATES") ? 76 : types.has("WORKS_IN") ? 68 : types.has("INFLUENCES") ? 64 : 38;
    const evidenceStrength = Math.min(100, 20 + node.evidenceIds.length * 18 + related.reduce((sum, edge) => sum + edge.confidence * 10, 0));
    const buyingSignal = types.has("CONTROLS_VENDOR_PROCESS") || linkedNodes.some((item) => item.type === "Tender") ? 88 : linkedNodes.some((item) => item.type === "Project") ? 72 : linkedNodes.some((item) => item.type === "Technology") ? 58 : 36;
    const reachability = linkedNodes.some((item) => ["Partner", "Event", "Tender"].includes(item.type)) ? 82 : Math.min(74, 35 + related.length * 8);
    const score = Math.round(problemOwnership * 0.35 + evidenceStrength * 0.3 + buyingSignal * 0.2 + reachability * 0.15);
    return {
      id: `stakeholder-${node.id}`,
      nodeId: node.id,
      label: node.label,
      role: node.type === "Person" ? "Publicly identified person" : "Buying-center role",
      score,
      problemOwnership,
      evidenceStrength: Math.round(evidenceStrength),
      buyingSignal,
      reachability,
      rationale: `Ranked from explicit problem links, ${node.evidenceIds.length + related.flatMap((edge) => edge.evidenceIds).length} evidence references, buying signals, and graph reachability.`,
      unknowns: node.unknowns ?? ["Purchasing authority is not established."],
      evidenceIds: [...new Set([...node.evidenceIds, ...related.flatMap((edge) => edge.evidenceIds)])],
    };
  }).sort((a, b) => b.score - a.score).slice(0, 8);
}

function findEntryPaths(nodes: AtlasNode[], edges: AtlasEdge[]): EntryPath[] {
  const starters = nodes.filter((node) => ["Partner", "Event", "Tender"].includes(node.type));
  const targets = new Set(nodes.filter((node) => node.type === "Function" || node.type === "BusinessUnit").map((node) => node.id));
  const adjacency = new Map<string, AtlasEdge[]>();
  for (const edge of edges) {
    adjacency.set(edge.source, [...(adjacency.get(edge.source) ?? []), edge]);
    adjacency.set(edge.target, [...(adjacency.get(edge.target) ?? []), edge]);
  }
  const paths: EntryPath[] = [];
  for (const start of starters) {
    const queue: string[][] = [[start.id]];
    const seen = new Set<string>([start.id]);
    while (queue.length) {
      const path = queue.shift()!;
      const tail = path[path.length - 1];
      if (path.length > 1 && targets.has(tail)) {
        const pathEdges = path.slice(1).map((id, index) => (adjacency.get(path[index]) ?? []).find((edge) => edge.source === id || edge.target === id)).filter(Boolean) as AtlasEdge[];
        const confirmed = pathEdges.every((edge) => edge.status === "confirmed");
        paths.push({
          id: `path-${start.id}-${tail}`,
          title: `${start.label} → ${nodes.find((node) => node.id === tail)?.label ?? "buying center"}`,
          summary: `A ${path.length - 1}-hop route grounded in ${new Set(pathEdges.flatMap((edge) => edge.evidenceIds)).size} source references. Validate the final introduction before outreach.`,
          nodeIds: path,
          confidence: confirmed ? "confirmed" : "inferred",
          evidenceIds: [...new Set(pathEdges.flatMap((edge) => edge.evidenceIds))],
        });
        break;
      }
      if (path.length >= 5) continue;
      for (const edge of adjacency.get(tail) ?? []) {
        const next = edge.source === tail ? edge.target : edge.source;
        if (!seen.has(next)) { seen.add(next); queue.push([...path, next]); }
      }
    }
  }
  return paths.slice(0, 5);
}

export async function runResearch(input: ResearchRequest): Promise<ResearchGraph> {
  const createdAt = new Date().toISOString();
  const synonyms = await expandProductTerms(input.product);
  const queries = buildQueries(input.company, synonyms, input.geography);
  const provider = getSearchProvider();
  const warnings: string[] = [];

  if (!provider) warnings.push("No web search provider is configured. Add TAVILY_API_KEY or BRAVE_SEARCH_API_KEY to run live discovery.");
  if (!process.env.OPENAI_API_KEY) warnings.push("OPENAI_API_KEY is not configured. Structured fact extraction was skipped.");

  const discovered: SearchResult[] = [];
  if (provider) {
    const batches = await Promise.allSettled(queries.slice(0, 7).map((query) => provider.search(query, 4)));
    for (const batch of batches) {
      if (batch.status === "fulfilled") discovered.push(...batch.value);
      else warnings.push(batch.reason instanceof Error ? batch.reason.message : "A discovery query failed.");
    }
  }
  const deduped = [...new Map(discovered.filter((item) => /^https?:\/\//.test(item.url)).map((item) => [item.url.split("#")[0], item])).values()].slice(0, 12);
  const retrieved = await Promise.all(deduped.map(retrieve));
  const observedAt = createdAt.slice(0, 10);
  const evidence: AtlasEvidence[] = retrieved.map((source, index) => ({
    id: `source-${index + 1}`,
    url: source.url,
    title: source.title,
    excerpt: (source.retrievedText || source.snippet).slice(0, 420),
    locator: source.locator,
    observedAt,
    sourceType: source.sourceType ?? "other",
    available: source.available,
  }));

  let facts: ExtractedFactSet | null = null;
  if (process.env.OPENAI_API_KEY && retrieved.length) {
    try { facts = await extractFacts(input.company, input.product, retrieved); }
    catch (error) { warnings.push(error instanceof Error ? error.message : "Structured extraction failed."); }
  }
  const { nodes, edges } = resolveFacts(input.company, facts, evidence);
  if (!retrieved.length) warnings.push("No public sources were returned. The graph contains only the supplied target and explicit unknowns.");
  if (retrieved.length && !facts) warnings.push("Sources were discovered, but no structured facts were extracted. Source records remain available for review.");

  return {
    id: `research-${Date.now()}`,
    company: input.company,
    product: input.product,
    geography: input.geography,
    createdAt,
    illustrative: false,
    provider: provider?.name ?? "Not configured",
    nodes,
    edges,
    evidence,
    stakeholders: scoreStakeholders(nodes, edges),
    entryPaths: findEntryPaths(nodes, edges),
    queries,
    synonyms,
    warnings,
  };
}
