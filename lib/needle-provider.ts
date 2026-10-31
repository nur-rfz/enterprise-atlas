import type { AtlasEdge, AtlasEvidence, AtlasNode, GraphPatch } from "./atlas-types";

const NEEDLE_BASE_URL = "https://needle.app/api/v1";

type UnknownRecord = Record<string, unknown>;

export interface NeedleStatus {
  configured: boolean;
  connectedAccountConfigured: boolean;
  mode: "classic" | "sales_navigator";
  message: string;
}

function text(value: unknown): string | undefined {
  return typeof value === "string" && value.trim() ? value.trim() : undefined;
}

function record(value: unknown): UnknownRecord {
  return value && typeof value === "object" ? value as UnknownRecord : {};
}

function slug(value: string) {
  return value.toLowerCase().normalize("NFKD").replace(/[^a-z0-9]+/g, "-").replace(/(^-|-$)/g, "").slice(0, 64) || "person";
}

export function getNeedleStatus(): NeedleStatus {
  const configured = Boolean(process.env.NEEDLE_API_KEY);
  const connectedAccountConfigured = Boolean(process.env.NEEDLE_CONNECTED_ACCOUNT_ID);
  const mode = process.env.NEEDLE_MODE === "sales_navigator" ? "sales_navigator" : "classic";
  return {
    configured,
    connectedAccountConfigured,
    mode,
    message: configured
      ? "Needle is configured for read-only LinkedIn enrichment. No messaging endpoints are used."
      : "Add NEEDLE_API_KEY and optionally NEEDLE_CONNECTED_ACCOUNT_ID to enable licensed LinkedIn enrichment.",
  };
}

async function needleRequest(path: string, init?: RequestInit) {
  const apiKey = process.env.NEEDLE_API_KEY;
  if (!apiKey) throw new Error("NEEDLE_API_KEY is not configured.");
  const response = await fetch(`${NEEDLE_BASE_URL}${path}`, {
    ...init,
    headers: { Authorization: `Bearer ${apiKey}`, "content-type": "application/json", ...(init?.headers ?? {}) },
    signal: AbortSignal.timeout(30_000),
  });
  if (!response.ok) {
    const detail = (await response.text()).slice(0, 220);
    throw new Error(`Needle request failed (${response.status})${detail ? `: ${detail}` : ""}`);
  }
  return response.json() as Promise<UnknownRecord>;
}

async function resolveConnectedAccountId(): Promise<string> {
  if (process.env.NEEDLE_CONNECTED_ACCOUNT_ID) return process.env.NEEDLE_CONNECTED_ACCOUNT_ID;
  const data = await needleRequest("/connected-accounts?limit=100");
  const accounts = Array.isArray(data.connectedAccounts) ? data.connectedAccounts.map(record) : [];
  const linkedin = accounts.find((account) => /linkedin/i.test(String(account.provider ?? account.type ?? account.name ?? ""))) ?? accounts[0];
  const id = text(linkedin?.id) ?? text(linkedin?.connectedAccountId);
  if (!id) throw new Error("No connected LinkedIn account was returned by Needle. Configure NEEDLE_CONNECTED_ACCOUNT_ID.");
  return id;
}

function normalizeHit(hitValue: unknown) {
  const hit = record(hitValue);
  const current = record(hit.currentPosition ?? hit.position ?? hit.experience);
  const firstName = text(hit.firstName);
  const lastName = text(hit.lastName);
  const name = text(hit.fullName) ?? text(hit.name) ?? [firstName, lastName].filter(Boolean).join(" ");
  return {
    id: text(hit.id) ?? text(hit.publicIdentifier) ?? slug(name || "person"),
    name,
    title: text(hit.headline) ?? text(hit.title) ?? text(current.title),
    company: text(hit.companyName) ?? text(hit.company) ?? text(current.companyName) ?? text(current.company),
    location: text(hit.locationName) ?? text(hit.location),
    profileUrl: text(hit.profileUrl) ?? text(hit.linkedinUrl) ?? text(hit.url),
  };
}

export async function searchNeedlePeople(input: { company: string; keywords: string[]; geography?: string }): Promise<GraphPatch> {
  const connectedAccountId = await resolveConnectedAccountId();
  const mode = getNeedleStatus().mode;
  const endpoint = mode === "sales_navigator" ? "/linkedin/sales-navigator/people/search" : "/linkedin/people/search";
  const queryGroups = [...new Set(input.keywords.map((item) => item.trim()).filter(Boolean))].slice(0, 5);
  const warnings: string[] = [];
  const hits: ReturnType<typeof normalizeHit>[] = [];

  for (const keywords of queryGroups) {
    try {
      const body: UnknownRecord = { connectedAccountId, keywords, limit: 10 };
      if (mode === "classic") {
        body.advancedKeywords = { company: input.company };
        if (input.geography) body.locations = [input.geography];
      } else {
        body.currentCompanies = [input.company];
        if (input.geography) body.geographies = [input.geography];
      }
      const data = await needleRequest(endpoint, { method: "POST", body: JSON.stringify(body) });
      const batch = Array.isArray(data.hits) ? data.hits : Array.isArray(data.results) ? data.results : [];
      hits.push(...batch.map(normalizeHit).filter((item) => item.name));
    } catch (error) {
      warnings.push(error instanceof Error ? error.message : `Needle search failed for ${keywords}.`);
    }
  }

  const unique = [...new Map(hits.map((hit) => [`${hit.name.toLowerCase()}|${(hit.profileUrl ?? "").toLowerCase()}`, hit])).values()];
  const evidence: AtlasEvidence[] = [];
  const nodes: AtlasNode[] = [];
  const edges: AtlasEdge[] = [];
  const observedAt = new Date().toISOString().slice(0, 10);

  for (const person of unique) {
    const personId = `needle-person-${slug(person.id || person.name)}`;
    const evidenceId = `needle-evidence-${slug(person.id || person.name)}`;
    const companyMatch = person.company?.toLowerCase().includes(input.company.toLowerCase().replace(/ group| ag/g, ""));
    evidence.push({
      id: evidenceId,
      url: person.profileUrl ?? "https://www.linkedin.com/search/results/people/",
      title: `${person.name}${person.title ? ` · ${person.title}` : ""}`,
      excerpt: [person.title, person.company, person.location].filter(Boolean).join(" · ") || "Licensed LinkedIn people-search result returned through Needle.",
      locator: "Needle LinkedIn people search",
      observedAt,
      sourceType: "enrichment",
      available: Boolean(person.profileUrl),
      provider: "Needle",
      access: "licensed",
    });
    nodes.push({
      id: personId,
      type: "Person",
      label: person.name,
      summary: [person.title, person.company, person.location].filter(Boolean).join(" · ") || "Licensed enrichment result.",
      evidenceIds: [evidenceId],
      unknowns: ["Problem ownership, purchasing influence, reporting line, and budget authority are not established by this profile result."],
      layers: ["organization"],
    });
    if (companyMatch) edges.push({
      id: `needle-edge-${slug(person.id || person.name)}`,
      source: personId,
      target: "company",
      type: "WORKS_IN",
      status: "confirmed",
      confidence: .78,
      evidenceIds: [evidenceId],
      rationale: "The licensed profile search result identifies the person with the target company. This does not establish internal reporting or buying authority.",
      layer: "organization",
    });
  }

  if (!unique.length && !warnings.length) warnings.push("Needle returned no matching people for the selected search clusters.");
  return { provider: `Needle LinkedIn (${mode})`, nodes, edges, evidence, warnings };
}
