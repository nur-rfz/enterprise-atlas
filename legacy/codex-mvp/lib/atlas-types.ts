export const NODE_TYPES = [
  "Company",
  "BusinessUnit",
  "Function",
  "Person",
  "Role",
  "Project",
  "Technology",
  "Partner",
  "Event",
  "Tender",
  "Evidence",
] as const;

export const EDGE_TYPES = [
  "BELONGS_TO",
  "WORKS_IN",
  "REPORTS_TO",
  "OWNS_PROJECT",
  "CONTRIBUTED_TO",
  "SPOKE_ABOUT",
  "PARTNERS_WITH",
  "USES_TECH",
  "RELATED_TO",
  "PROCUREMENT_CONTACT_FOR",
  "INFLUENCES",
  "POTENTIAL_ENTRY_VIA",
  "SPONSORS_PROJECT",
  "EVALUATES",
  "CONTROLS_VENDOR_PROCESS",
  "PROCURED",
  "INTRODUCES_TO",
] as const;

export type NodeType = (typeof NODE_TYPES)[number];
export type EdgeType = (typeof EDGE_TYPES)[number];
export type ClaimStatus = "confirmed" | "inferred" | "uncertain";
export type GraphLayer = "organization" | "buying_center" | "ecosystem";
export type SourceType = "company" | "job" | "event" | "partner" | "tender" | "association" | "research" | "enrichment" | "other";

export interface AtlasEvidence {
  id: string;
  url: string;
  title: string;
  excerpt: string;
  locator?: string;
  observedAt: string;
  sourceType: SourceType;
  available: boolean;
  provider?: string;
  access?: "public" | "licensed";
}

export interface AtlasNode {
  id: string;
  type: NodeType;
  label: string;
  summary: string;
  evidenceIds: string[];
  aliases?: string[];
  unknowns?: string[];
  layers?: GraphLayer[];
}

export interface AtlasEdge {
  id: string;
  source: string;
  target: string;
  type: EdgeType;
  status: ClaimStatus;
  confidence: number;
  evidenceIds: string[];
  rationale: string;
  layer?: GraphLayer;
}

export interface StakeholderCandidate {
  id: string;
  nodeId: string;
  label: string;
  role: string;
  score: number;
  problemOwnership: number;
  evidenceStrength: number;
  buyingSignal: number;
  reachability: number;
  rationale: string;
  unknowns: string[];
  evidenceIds: string[];
}

export interface EntryPath {
  id: string;
  title: string;
  summary: string;
  nodeIds: string[];
  confidence: ClaimStatus;
  evidenceIds: string[];
}

export interface ResearchGraph {
  id: string;
  company: string;
  product: string;
  geography?: string;
  createdAt: string;
  illustrative: boolean;
  provider: string;
  nodes: AtlasNode[];
  edges: AtlasEdge[];
  evidence: AtlasEvidence[];
  stakeholders: StakeholderCandidate[];
  entryPaths: EntryPath[];
  queries: string[];
  synonyms: string[];
  warnings: string[];
}

export interface ResearchRequest {
  company: string;
  product: string;
  geography?: string;
}

export interface SearchResult {
  url: string;
  title: string;
  snippet: string;
  rawContent?: string;
  publishedAt?: string;
  sourceType?: SourceType;
}

export interface ExtractedFactSet {
  nodes: Array<Omit<AtlasNode, "id" | "evidenceIds"> & { key: string; evidenceIndexes: number[] }>;
  edges: Array<Omit<AtlasEdge, "id" | "source" | "target" | "evidenceIds"> & { sourceKey: string; targetKey: string; evidenceIndexes: number[] }>;
}

export interface GraphPatch {
  provider: string;
  nodes: AtlasNode[];
  edges: AtlasEdge[];
  evidence: AtlasEvidence[];
  warnings: string[];
}
