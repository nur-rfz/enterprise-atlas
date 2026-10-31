"use client";

import { useEffect, useMemo, useState } from "react";
import { GraphView, type GraphSelection } from "./GraphView";
import { sampleGraph } from "../lib/sample-graph";
import type { AtlasEvidence, ClaimStatus, ResearchGraph } from "../lib/atlas-types";

const STATUS_OPTIONS: Array<{ value: ClaimStatus; label: string }> = [
  { value: "confirmed", label: "Confirmed" },
  { value: "inferred", label: "AI inference" },
  { value: "uncertain", label: "Uncertain" },
];

const TYPE_COLORS: Record<string, string> = {
  Company: "#183f31", BusinessUnit: "#9ed6ef", Function: "#c9f3cf", Person: "#f4c7c3", Role: "#e3d5f5",
  Project: "#efb17d", Technology: "#eedbc4", Partner: "#dff467", Event: "#f4d37c", Tender: "#b8e4da", Evidence: "#e2e5df",
};

function getEvidence(graph: ResearchGraph, ids: string[]): AtlasEvidence[] {
  const wanted = new Set(ids);
  return graph.evidence.filter((item) => wanted.has(item.id));
}

function initials(value: string) {
  return value.split(/\s+/).map((part) => part[0]).join("").slice(0, 2).toUpperCase();
}

export function AtlasApp() {
  const [graph, setGraph] = useState<ResearchGraph>(sampleGraph);
  const [company, setCompany] = useState(sampleGraph.company);
  const [product, setProduct] = useState(sampleGraph.product);
  const [geography, setGeography] = useState(sampleGraph.geography ?? "");
  const [selection, setSelection] = useState<GraphSelection>({ kind: "node", id: sampleGraph.nodes[2].id });
  const [statuses, setStatuses] = useState<Set<ClaimStatus>>(new Set(["confirmed", "inferred", "uncertain"]));
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showMethod, setShowMethod] = useState(false);

  useEffect(() => {
    try {
      const stored = window.localStorage.getItem("enterprise-atlas:last-research");
      if (!stored) return;
      const parsed = JSON.parse(stored) as ResearchGraph;
      if (parsed.nodes?.length && parsed.company && !parsed.illustrative) {
        setGraph(parsed);
        setCompany(parsed.company);
        setProduct(parsed.product);
        setGeography(parsed.geography ?? "");
        setSelection({ kind: "node", id: parsed.nodes[0].id });
      }
    } catch { /* Device-local persistence is optional. */ }
  }, []);

  const businessNodes = graph.nodes.filter((node) => node.type === "BusinessUnit" || node.type === "Function");
  const selectedNode = selection.kind === "node" ? graph.nodes.find((node) => node.id === selection.id) : undefined;
  const selectedEdge = selection.kind === "edge" ? graph.edges.find((edge) => edge.id === selection.id) : undefined;
  const incidentEdges = selectedNode ? graph.edges.filter((edge) => edge.source === selectedNode.id || edge.target === selectedNode.id) : [];
  const selectionEvidenceIds = selectedNode
    ? [...selectedNode.evidenceIds, ...incidentEdges.flatMap((edge) => edge.evidenceIds)]
    : selectedEdge?.evidenceIds ?? [];
  const selectionEvidence = getEvidence(graph, [...new Set(selectionEvidenceIds)]);
  const selectedTitle = selectedNode?.label ?? (selectedEdge ? `${graph.nodes.find((node) => node.id === selectedEdge.source)?.label ?? "Source"} → ${graph.nodes.find((node) => node.id === selectedEdge.target)?.label ?? "Target"}` : "Select an entity");
  const selectedSummary = selectedNode?.summary ?? selectedEdge?.rationale ?? "Choose a node or relationship to inspect its evidence.";
  const selectedStatus: ClaimStatus = selectedEdge?.status ?? (selectedNode?.evidenceIds.length ? "confirmed" : "uncertain");
  const selectedUnknowns = selectedNode?.unknowns ?? (selectedEdge?.status !== "confirmed" ? ["The relationship is not explicitly established by a public source."] : []);
  const sourceCoverage = graph.edges.length ? Math.round((graph.edges.filter((edge) => edge.evidenceIds.length).length / graph.edges.length) * 100) : 0;

  const nodeTypeLegend = useMemo(() => [...new Set(graph.nodes.map((node) => node.type))].slice(0, 6), [graph]);

  function toggleStatus(value: ClaimStatus) {
    setStatuses((current) => {
      const next = new Set(current);
      if (next.has(value) && next.size > 1) next.delete(value); else next.add(value);
      return next;
    });
  }

  async function runResearch(event: React.FormEvent) {
    event.preventDefault();
    if (!company.trim() || !product.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const response = await fetch("/api/research", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ company, product, geography }),
      });
      const data = await response.json() as ResearchGraph & { error?: string };
      if (!response.ok) throw new Error(data.error ?? "Research could not be completed.");
      setGraph(data);
      setSelection({ kind: "node", id: data.nodes[0]?.id ?? "target-company" });
      window.localStorage.setItem("enterprise-atlas:last-research", JSON.stringify(data));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Research could not be completed.");
    } finally {
      setLoading(false);
    }
  }

  function downloadGraph() {
    const blob = new Blob([JSON.stringify(graph, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `${graph.company.toLowerCase().replace(/[^a-z0-9]+/g, "-")}-atlas.json`;
    anchor.click();
    URL.revokeObjectURL(url);
  }

  return (
    <main className="atlas-shell">
      <header className="topbar">
        <a className="wordmark" href="#top" aria-label="Enterprise Atlas home"><span className="mark">EA</span> Enterprise Atlas</a>
        <div className="top-meta"><span className="live-dot" /> Public evidence intelligence</div>
        <button className="export-button" type="button" onClick={downloadGraph}>Export graph <span>↗</span></button>
      </header>

      <form className="query-bar" id="top" aria-label="Research query" onSubmit={runResearch}>
        <label className="field company-field"><span className="field-label">Target enterprise</span><input value={company} onChange={(event) => setCompany(event.target.value)} placeholder="e.g. Mercedes-Benz Group" /></label>
        <label className="field product-field"><span className="field-label">Startup product</span><input value={product} onChange={(event) => setProduct(event.target.value)} placeholder="Describe the product and problem it solves" /></label>
        <label className="field geo-field"><span className="field-label">Geography</span><input value={geography} onChange={(event) => setGeography(event.target.value)} placeholder="Optional" /></label>
        <button className="run-button" type="submit" disabled={loading}>{loading ? "Researching…" : "Run research"}<span>→</span></button>
      </form>

      {error && <div className="notice error-notice"><strong>Research stopped.</strong> {error}<button type="button" onClick={() => setError(null)} aria-label="Dismiss error">×</button></div>}
      {graph.illustrative && <div className="notice fixture-banner"><strong>Illustrative sample</strong><span>This fixture exists only for UI development. Roles are hypotheses, no people are named, and no reporting or purchasing authority is asserted.</span></div>}
      {!graph.illustrative && graph.warnings.length > 0 && <div className="notice warning-banner"><strong>{graph.warnings.length} research note{graph.warnings.length === 1 ? "" : "s"}</strong><span>{graph.warnings[0]}</span></div>}

      <section className="workspace">
        <aside className="left-panel panel">
          <div className="panel-title"><span>Business map</span><span>{businessNodes.length}</span></div>
          <div className="account-card"><div className="company-monogram">{initials(graph.company)}</div><div><strong>{graph.company}</strong><span>{graph.nodes.length} mapped entities</span></div></div>
          <nav className="unit-nav" aria-label="Business units and functions">
            {businessNodes.length ? businessNodes.map((node) => (
              <button type="button" key={node.id} className={selection.id === node.id ? "active" : ""} onClick={() => setSelection({ kind: "node", id: node.id })}>
                <span className="unit-icon" style={{ background: TYPE_COLORS[node.type] }}>{node.type === "BusinessUnit" ? "BU" : "FN"}</span><span>{node.label}</span><em>{graph.edges.filter((edge) => edge.source === node.id || edge.target === node.id).length}</em>
              </button>
            )) : <div className="empty-nav">No functions verified yet.</div>}
          </nav>
          <div className="filter-block"><span className="eyebrow">Evidence status</span>{STATUS_OPTIONS.map((option) => <label key={option.value}><input type="checkbox" checked={statuses.has(option.value)} onChange={() => toggleStatus(option.value)} /> {option.label}</label>)}</div>
          <div className="filter-block source-mix"><span className="eyebrow">Sources observed</span>{Object.entries(graph.evidence.reduce<Record<string, number>>((counts, item) => ({ ...counts, [item.sourceType]: (counts[item.sourceType] ?? 0) + 1 }), {})).map(([type, count]) => <div key={type}><span>{type}</span><b>{count}</b></div>)}{!graph.evidence.length && <p>No sources collected.</p>}</div>
          <div className="fixture-note"><span>{graph.illustrative ? "Illustrative fixture" : `Live run · ${graph.provider}`}</span><p>{graph.illustrative ? "Use Run research to replace this sample with a fresh evidence graph." : `Observed ${new Date(graph.createdAt).toLocaleDateString()}. Saved on this device.`}</p></div>
        </aside>

        <section className="graph-panel panel">
          <div className="graph-toolbar"><div><span className="eyebrow">Buying-center graph</span><h1>{graph.nodes.length > 1 ? "Who owns the problem?" : "Evidence still needed"}</h1></div><div className="legend">{nodeTypeLegend.map((type) => <span key={type}><i style={{ background: TYPE_COLORS[type] }} />{type.replace(/([a-z])([A-Z])/g, "$1 $2")}</span>)}</div></div>
          <div className="graph-canvas">
            <div className="graph-grid" />
            <GraphView graph={graph} selection={selection} statuses={statuses} onSelect={setSelection} />
            {loading && <div className="research-overlay"><div className="research-card"><span className="research-spinner" /><strong>Building the evidence graph</strong><div className="research-steps"><span>Expanding the business problem</span><span>Discovering public sources</span><span>Extracting traceable facts</span><span>Ranking credible routes</span></div><small>No outreach is sent.</small></div></div>}
          </div>
          <div className="graph-footer"><span><b>{graph.nodes.length}</b> entities</span><span><b>{graph.edges.length}</b> relationships</span><span><b>{graph.evidence.length}</b> sources</span><span className="coverage">Evidence coverage <b>{sourceCoverage}%</b></span></div>
        </section>

        <aside className="right-panel panel">
          <div className="panel-title"><span>Evidence detail</span><span className={`status-pill ${selectedStatus}`}>{selectedStatus}</span></div>
          <div className="entity-heading"><span className="entity-type">{selectedNode?.type ?? selectedEdge?.type.replaceAll("_", " ") ?? "SELECTION"}</span><h2>{selectedTitle}</h2><p>{selectedSummary}</p></div>
          {(selectedUnknowns.length > 0 || !selectedNode?.evidenceIds.length) && <div className="unknown-callout"><span>!</span><p><strong>Unknowns remain</strong>{selectedUnknowns[0] ?? "This entity has no direct public evidence. Inspect related relationships before relying on it."}</p></div>}
          {selectedEdge && <div className="confidence-block"><span>Relationship confidence</span><strong>{Math.round(selectedEdge.confidence * 100)}%</strong><div><i style={{ width: `${selectedEdge.confidence * 100}%` }} /></div><small>Confidence is evidence quality, not purchasing authority.</small></div>}
          <div className="evidence-list"><span className="eyebrow">Supporting evidence · {selectionEvidence.length}</span>{selectionEvidence.map((item) => <article key={item.id}><div className="source-icon">{item.sourceType[0].toUpperCase()}</div><div><strong>{item.title}</strong><p>{item.excerpt}</p><small>{item.observedAt}{item.locator ? ` · ${item.locator}` : ""}</small><a href={item.url} target="_blank" rel="noreferrer">View source ↗</a></div></article>)}{!selectionEvidence.length && <div className="empty-evidence"><strong>No supporting source attached</strong><p>Treat this selection as a research hypothesis, not a material claim.</p></div>}</div>
        </aside>
      </section>

      <section className="insights-grid">
        <div className="insight-panel"><div className="section-heading"><div><span className="eyebrow">Ranked stakeholders</span><h2>Buying committee candidates</h2></div><button type="button" onClick={() => setShowMethod(true)}>View methodology</button></div>
          <div className="stakeholder-row header"><span>Candidate</span><span>Evidence</span><span>Signal</span><span>Reach</span><span>Score</span></div>
          {graph.stakeholders.map((candidate, index) => <button type="button" className="stakeholder-row stakeholder-button" key={candidate.id} onClick={() => setSelection({ kind: "node", id: candidate.nodeId })}><span><b>{index + 1}</b><strong>{candidate.label}</strong><small>{candidate.role} · {candidate.unknowns[0] ?? "Authority unknown"}</small></span><span>{candidate.evidenceStrength}</span><span><i className="signal-dot" />{candidate.buyingSignal}</span><span>{candidate.reachability}</span><span><em>{candidate.score}</em></span></button>)}
          {!graph.stakeholders.length && <div className="empty-table"><strong>No stakeholder can be ranked yet.</strong><p>The app will not invent names or upgrade titles into authority.</p></div>}
        </div>
        <div className="paths-panel"><div className="section-heading"><div><span className="eyebrow">Recommended entry routes</span><h2>Credible paths in</h2></div><span>{graph.entryPaths.length} route{graph.entryPaths.length === 1 ? "" : "s"}</span></div>
          {graph.entryPaths.map((path, index) => <article className="path-card" key={path.id}><div className="path-number">{String(index + 1).padStart(2, "0")}</div><div><strong>{path.title}</strong><p>{path.summary}</p><div className="mini-path">{path.nodeIds.map((id, pathIndex) => <span className="path-fragment" key={id}><button type="button" onClick={() => setSelection({ kind: "node", id })}>{graph.nodes.find((node) => node.id === id)?.label ?? id}</button>{pathIndex < path.nodeIds.length - 1 && <b>→</b>}</span>)}</div></div><em className={path.confidence}>{path.confidence}</em></article>)}
          {!graph.entryPaths.length && <div className="empty-table"><strong>No evidence-backed path yet.</strong><p>Look for suppliers, partners, public events, or formal procurement processes.</p></div>}
        </div>
      </section>

      <section className="research-ledger">
        <div className="section-heading"><div><span className="eyebrow">Research ledger</span><h2>Queries &amp; source trail</h2></div><span>{graph.queries.length} searches · {graph.synonyms.length} problem terms</span></div>
        <div className="ledger-grid"><div><span className="eyebrow">Problem expansion</span><div className="chip-list">{graph.synonyms.map((term) => <span key={term}>{term}</span>)}</div></div><div><span className="eyebrow">Discovery queries</span><ol>{graph.queries.slice(0, 6).map((query) => <li key={query}>{query}</li>)}</ol></div><div><span className="eyebrow">Guardrails</span><ul><li>Public, normally retrievable sources only</li><li>No LinkedIn scraping or access bypass</li><li>No inferred budget or purchase authority</li><li>No automatic outreach</li></ul></div></div>
      </section>

      {showMethod && <div className="modal-backdrop" role="presentation" onMouseDown={() => setShowMethod(false)}><section className="method-modal" role="dialog" aria-modal="true" aria-labelledby="method-title" onMouseDown={(event) => event.stopPropagation()}><button className="modal-close" type="button" onClick={() => setShowMethod(false)} aria-label="Close methodology">×</button><span className="eyebrow">Transparent ranking</span><h2 id="method-title">Why a stakeholder ranks</h2><p>Scores are a prioritization aid, never proof of authority.</p><div className="formula-row"><span><b>35%</b> Problem ownership</span><span><b>30%</b> Evidence strength</span><span><b>20%</b> Buying signal</span><span><b>15%</b> Reachability</span></div><p className="method-note">People and roles without evidence remain visible as unknowns, but they cannot receive strong evidence scores. A job title or conference appearance alone never establishes budget or purchasing authority.</p></section></div>}
    </main>
  );
}
