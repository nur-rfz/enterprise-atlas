"use client";

import { useEffect, useMemo, useState } from "react";
import { GraphView, type GraphSelection } from "./GraphView";
import { mercedesGraph } from "../lib/mercedes-graph";
import { EDGE_TYPES, NODE_TYPES, type AtlasEdge, type AtlasEvidence, type AtlasNode, type ClaimStatus, type GraphLayer, type GraphPatch, type ResearchGraph } from "../lib/atlas-types";

const TYPE_COLORS: Record<string, string> = {
  Company: "#153d30", BusinessUnit: "#9ac9dd", Function: "#bde4c5", Person: "#e9b9b3", Role: "#d7cae8",
  Project: "#e7a66e", Technology: "#dec9ad", Partner: "#d9ec62", Event: "#e9c767", Tender: "#9bd3c7", Evidence: "#d7dad4",
};
const NEEDLE_CLUSTERS = ["aftersales data analytics", "warranty quality reliability", "data product AI", "IT architecture integration", "procurement supplier"];

type Modal = "research" | "node" | "edge" | "source" | "needle" | "duplicates" | null;
type InspectorTab = "properties" | "evidence" | "relationships";
type ResultTab = "stakeholders" | "paths" | "sources";
type NeedleStatus = { configured: boolean; connectedAccountConfigured: boolean; mode: string; message: string };

function normal(value: string) { return value.toLowerCase().normalize("NFKD").replace(/[^a-z0-9]+/g, " ").trim(); }
function slug(value: string) { return normal(value).replace(/\s+/g, "-").slice(0, 60) || "entity"; }
function initials(value: string) { return value.split(/\s+/).map((part) => part[0]).join("").slice(0, 2).toUpperCase(); }
function labelize(value: string) { return value.toLowerCase().replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase()); }
function evidenceFor(graph: ResearchGraph, ids: string[]) { const wanted = new Set(ids); return graph.evidence.filter((item) => wanted.has(item.id)); }

function mergePatch(graph: ResearchGraph, patch: GraphPatch): ResearchGraph {
  const evidence = [...graph.evidence];
  const evidenceMap = new Map(evidence.map((item) => [item.url, item.id]));
  const patchEvidenceIds = new Map<string, string>();
  for (const item of patch.evidence) {
    const existingId = evidenceMap.get(item.url);
    if (existingId) patchEvidenceIds.set(item.id, existingId);
    else { evidence.push(item); evidenceMap.set(item.url, item.id); patchEvidenceIds.set(item.id, item.id); }
  }
  const nodes = graph.nodes.map((node) => ({ ...node, evidenceIds: [...node.evidenceIds] }));
  const nodeIdMap = new Map<string, string>();
  const companyId = nodes.find((node) => node.type === "Company")?.id ?? "company";
  nodeIdMap.set("company", companyId); nodeIdMap.set("target-company", companyId);
  for (const incoming of patch.nodes) {
    const existing = nodes.find((node) => node.type === incoming.type && normal(node.label) === normal(incoming.label));
    const remappedEvidence = incoming.evidenceIds.map((id) => patchEvidenceIds.get(id) ?? id);
    if (existing) {
      existing.evidenceIds = [...new Set([...existing.evidenceIds, ...remappedEvidence])];
      existing.aliases = [...new Set([...(existing.aliases ?? []), ...(incoming.aliases ?? [])])];
      nodeIdMap.set(incoming.id, existing.id);
    } else {
      const id = nodes.some((node) => node.id === incoming.id) ? `${incoming.id}-${nodes.length + 1}` : incoming.id;
      nodes.push({ ...incoming, id, evidenceIds: remappedEvidence }); nodeIdMap.set(incoming.id, id);
    }
  }
  const edges = [...graph.edges];
  for (const incoming of patch.edges) {
    const source = nodeIdMap.get(incoming.source) ?? incoming.source;
    const target = nodeIdMap.get(incoming.target) ?? incoming.target;
    if (!nodes.some((node) => node.id === source) || !nodes.some((node) => node.id === target)) continue;
    if (edges.some((edge) => edge.source === source && edge.target === target && edge.type === incoming.type)) continue;
    edges.push({ ...incoming, id: edges.some((edge) => edge.id === incoming.id) ? `${incoming.id}-${edges.length + 1}` : incoming.id, source, target, evidenceIds: incoming.evidenceIds.map((id) => patchEvidenceIds.get(id) ?? id) });
  }
  return { ...graph, provider: `${graph.provider} + ${patch.provider}`, nodes, edges, evidence, warnings: [...new Set([...graph.warnings, ...patch.warnings])] };
}

function ModalFrame({ title, eyebrow, onClose, children }: { title: string; eyebrow: string; onClose: () => void; children: React.ReactNode }) {
  return <div className="modal-backdrop"><button className="modal-scrim" type="button" onClick={onClose} aria-label="Close dialog" /><section className="workbench-modal" role="dialog" aria-modal="true" aria-label={title}><div className="modal-heading"><div><span>{eyebrow}</span><h2>{title}</h2></div><button type="button" onClick={onClose} aria-label="Close">×</button></div>{children}</section></div>;
}

export function AtlasApp() {
  const [graph, setGraph] = useState<ResearchGraph>(mercedesGraph);
  const [selection, setSelection] = useState<GraphSelection>({ kind: "node", id: "aftersales" });
  const [activeLayer, setActiveLayer] = useState<GraphLayer | "combined">("combined");
  const [statuses, setStatuses] = useState<Set<ClaimStatus>>(new Set(["confirmed", "inferred", "uncertain"]));
  const [modal, setModal] = useState<Modal>(null);
  const [inspectorTab, setInspectorTab] = useState<InspectorTab>("properties");
  const [resultTab, setResultTab] = useState<ResultTab>("stakeholders");
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [hydrated, setHydrated] = useState(false);
  const [needleStatus, setNeedleStatus] = useState<NeedleStatus | null>(null);
  const [needleKeywords, setNeedleKeywords] = useState(NEEDLE_CLUSTERS.join("\n"));

  useEffect(() => {
    let parsed: ResearchGraph | null = null;
    try {
      const stored = window.localStorage.getItem("enterprise-atlas:workspace");
      if (stored) parsed = JSON.parse(stored) as ResearchGraph;
    } catch { /* Local persistence is optional. */ }
    queueMicrotask(() => {
      if (parsed?.nodes?.length && parsed.edges && parsed.evidence) setGraph(parsed);
      setHydrated(true);
    });
  }, []);
  useEffect(() => { if (hydrated) window.localStorage.setItem("enterprise-atlas:workspace", JSON.stringify(graph)); }, [graph, hydrated]);

  const selectedNode = selection.kind === "node" ? graph.nodes.find((node) => node.id === selection.id) : undefined;
  const selectedEdge = selection.kind === "edge" ? graph.edges.find((edge) => edge.id === selection.id) : undefined;
  const incidentEdges = selectedNode ? graph.edges.filter((edge) => edge.source === selectedNode.id || edge.target === selectedNode.id) : [];
  const selectedEvidence = evidenceFor(graph, [...new Set(selectedNode ? [...selectedNode.evidenceIds, ...incidentEdges.flatMap((edge) => edge.evidenceIds)] : selectedEdge?.evidenceIds ?? [])]);
  const selectedStatus: ClaimStatus = selectedEdge?.status ?? (selectedNode?.evidenceIds.length ? "confirmed" : "uncertain");
  const selectedTitle = selectedNode?.label ?? (selectedEdge ? `${graph.nodes.find((node) => node.id === selectedEdge.source)?.label} → ${graph.nodes.find((node) => node.id === selectedEdge.target)?.label}` : "Nothing selected");
  const sourceCoverage = graph.edges.length ? Math.round(graph.edges.filter((edge) => edge.evidenceIds.length).length / graph.edges.length * 100) : 0;
  const businessNodes = graph.nodes.filter((node) => node.type === "BusinessUnit" || node.type === "Function");
  const duplicates = useMemo(() => graph.nodes.flatMap((node, index) => graph.nodes.slice(index + 1).filter((candidate) => candidate.type === node.type && (normal(candidate.label) === normal(node.label) || candidate.aliases?.some((alias) => normal(alias) === normal(node.label)))).map((candidate) => [node, candidate] as [AtlasNode, AtlasNode])), [graph.nodes]);
  const visibleGraph = useMemo<ResearchGraph>(() => {
    if (activeLayer === "combined") return graph;
    const allowedLayers: GraphLayer[] = activeLayer === "buying_center" ? ["buying_center", "ecosystem"] : ["organization"];
    const nodes = graph.nodes.filter((node) => !node.layers || node.layers.some((layer) => allowedLayers.includes(layer)));
    const ids = new Set(nodes.map((node) => node.id));
    return { ...graph, nodes, edges: graph.edges.filter((edge) => (!edge.layer || allowedLayers.includes(edge.layer)) && ids.has(edge.source) && ids.has(edge.target)) };
  }, [activeLayer, graph]);

  function updateGraph(next: ResearchGraph) { setGraph(next); }
  function select(next: GraphSelection) { setSelection(next); setInspectorTab("properties"); }
  function toggleStatus(status: ClaimStatus) { setStatuses((current) => { const next = new Set(current); if (next.has(status) && next.size > 1) next.delete(status); else next.add(status); return next; }); }
  function downloadGraph() { const url = URL.createObjectURL(new Blob([JSON.stringify(graph, null, 2)], { type: "application/json" })); const anchor = document.createElement("a"); anchor.href = url; anchor.download = `${slug(graph.company)}-ontology.json`; anchor.click(); URL.revokeObjectURL(url); }

  async function openNeedle() {
    setModal("needle"); setNeedleStatus(null); setError(null);
    try { const response = await fetch("/api/enrichment/needle"); setNeedleStatus(await response.json() as NeedleStatus); }
    catch { setNeedleStatus({ configured: false, connectedAccountConfigured: false, mode: "classic", message: "Needle status could not be loaded." }); }
  }

  async function runNeedle() {
    setBusy("needle"); setError(null);
    try {
      const response = await fetch("/api/enrichment/needle", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ company: graph.company, geography: graph.geography, keywords: needleKeywords.split("\n").map((item) => item.trim()).filter(Boolean) }) });
      const data = await response.json() as GraphPatch & { error?: string };
      if (!response.ok) throw new Error(data.error ?? "Needle enrichment failed.");
      updateGraph(mergePatch(graph, data)); setModal(null);
    } catch (caught) { setError(caught instanceof Error ? caught.message : "Needle enrichment failed."); }
    finally { setBusy(null); }
  }

  async function runResearch(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy("research"); setError(null); const form = new FormData(event.currentTarget);
    try {
      const response = await fetch("/api/research", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ company: form.get("company"), product: form.get("product"), geography: form.get("geography") }) });
      const data = await response.json() as ResearchGraph & { error?: string };
      if (!response.ok) throw new Error(data.error ?? "Research failed.");
      updateGraph(data); setSelection({ kind: "node", id: data.nodes[0]?.id ?? "target-company" }); setModal(null);
    } catch (caught) { setError(caught instanceof Error ? caught.message : "Research failed."); }
    finally { setBusy(null); }
  }

  function addNode(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault(); const form = new FormData(event.currentTarget); const label = String(form.get("label") ?? "").trim(); if (!label) return;
    const type = String(form.get("type")) as AtlasNode["type"]; const idBase = `${slug(type)}-${slug(label)}`; const id = graph.nodes.some((node) => node.id === idBase) ? `${idBase}-${Date.now().toString(36)}` : idBase;
    const node: AtlasNode = { id, type, label, summary: String(form.get("summary") || "Research hypothesis added by the analyst."), evidenceIds: [], unknowns: ["This analyst-added entity has no attached evidence yet."], layers: [String(form.get("layer")) as GraphLayer] };
    updateGraph({ ...graph, nodes: [...graph.nodes, node] }); setSelection({ kind: "node", id }); setModal(null);
  }

  function addEdge(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault(); const form = new FormData(event.currentTarget); const evidenceId = String(form.get("evidenceId") ?? ""); if (!evidenceId) { setError("A source is required for every relationship."); return; }
    const source = String(form.get("source")); const target = String(form.get("target")); if (source === target) { setError("A relationship must connect two different entities."); return; }
    const edge: AtlasEdge = { id: `edge-${Date.now().toString(36)}`, source, target, type: String(form.get("type")) as AtlasEdge["type"], status: String(form.get("status")) as ClaimStatus, confidence: Number(form.get("confidence")) / 100, evidenceIds: [evidenceId], rationale: String(form.get("rationale") || "Analyst-added relationship; review the attached evidence."), layer: String(form.get("layer")) as GraphLayer };
    updateGraph({ ...graph, edges: [...graph.edges, edge] }); setSelection({ kind: "edge", id: edge.id }); setModal(null);
  }

  async function ingestSource(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy("source"); setError(null); const form = new FormData(event.currentTarget);
    try {
      const response = await fetch("/api/ingest", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ url: form.get("url") }) });
      const data = await response.json() as AtlasEvidence & { error?: string };
      if (!response.ok) throw new Error(data.error ?? "Source ingestion failed.");
      updateGraph({ ...graph, evidence: [...graph.evidence.filter((item) => item.url !== data.url), data] }); setModal(null); setResultTab("sources");
    } catch (caught) { setError(caught instanceof Error ? caught.message : "Source ingestion failed."); }
    finally { setBusy(null); }
  }

  function mergeDuplicate(keep: AtlasNode, remove: AtlasNode) {
    const nodes = graph.nodes.filter((node) => node.id !== remove.id).map((node) => node.id === keep.id ? { ...node, evidenceIds: [...new Set([...node.evidenceIds, ...remove.evidenceIds])], aliases: [...new Set([...(node.aliases ?? []), remove.label, ...(remove.aliases ?? [])])] } : node);
    const edges = graph.edges.map((edge) => ({ ...edge, source: edge.source === remove.id ? keep.id : edge.source, target: edge.target === remove.id ? keep.id : edge.target })).filter((edge, index, all) => all.findIndex((item) => item.source === edge.source && item.target === edge.target && item.type === edge.type) === index && edge.source !== edge.target);
    updateGraph({ ...graph, nodes, edges }); setSelection({ kind: "node", id: keep.id });
  }

  return <main className="atlas-shell">
    <header className="topbar"><a className="wordmark" href="#workspace"><span>EA</span><strong>Enterprise Atlas</strong></a><div className="top-context"><span className="live-dot" />Evidence workspace <b>/</b> Mercedes-Benz</div><div className="top-actions"><button type="button" onClick={() => setModal("research")}>New research</button><button className="primary" type="button" onClick={downloadGraph}>Export ↗</button></div></header>
    {error && <div className="global-alert"><span>{error}</span><button type="button" onClick={() => setError(null)}>×</button></div>}

    <section className="workbench" id="workspace">
      <aside className="sidebar">
        <div className="workspace-label"><span>WORKSPACE 01</span><strong>{graph.company}</strong><small>{graph.geography || "Global research"}</small></div>
        <nav className="main-nav" aria-label="Workspace sections"><button className="active" type="button"><span>⌘</span>Ontology</button><button type="button" onClick={() => { setResultTab("sources"); document.getElementById("results")?.scrollIntoView({ behavior: "smooth" }); }}><span>◫</span>Evidence <b>{graph.evidence.length}</b></button><button type="button" onClick={() => { setResultTab("stakeholders"); document.getElementById("results")?.scrollIntoView({ behavior: "smooth" }); }}><span>◎</span>People <b>{graph.nodes.filter((node) => node.type === "Person").length}</b></button><button type="button" onClick={() => setModal("duplicates")}><span>◇</span>Merge queue <b>{duplicates.length}</b></button></nav>
        <div className="sidebar-section"><div className="sidebar-heading"><span>Business map</span><b>{businessNodes.length}</b></div>{businessNodes.map((node) => <button type="button" className={`entity-nav ${selection.id === node.id ? "active" : ""}`} key={node.id} onClick={() => select({ kind: "node", id: node.id })}><i style={{ background: TYPE_COLORS[node.type] }} /><span>{node.label}</span></button>)}</div>
        <div className="sidebar-section status-filters"><div className="sidebar-heading"><span>Relationship status</span></div>{(["confirmed", "inferred", "uncertain"] as ClaimStatus[]).map((status) => <label key={status}><input type="checkbox" checked={statuses.has(status)} onChange={() => toggleStatus(status)} /><span>{labelize(status)}</span></label>)}</div>
        <div className="connection-stack"><div><span className="connection-dot connected" /><p><strong>Public evidence</strong><small>{graph.evidence.filter((item) => item.access !== "licensed").length} sources indexed</small></p></div><button type="button" onClick={openNeedle}><span className={`connection-dot ${graph.evidence.some((item) => item.provider === "Needle") ? "connected" : ""}`} /><p><strong>Needle enrichment</strong><small>{graph.evidence.some((item) => item.provider === "Needle") ? "Licensed data loaded" : "Connect read-only"}</small></p><b>→</b></button></div>
      </aside>

      <section className="canvas-column">
        <div className="workspace-header"><div><span className="kicker">TARGET ACCOUNT / AFTERSALES INTELLIGENCE</span><h1>{graph.company}</h1><p>{graph.product}</p></div><div className="research-meta"><span><b>{graph.nodes.length}</b> entities</span><span><b>{graph.edges.length}</b> relations</span><span><b>{sourceCoverage}%</b> sourced</span></div></div>
        <div className="canvas-toolbar"><div className="layer-tabs" aria-label="Ontology layer">{(["organization", "buying_center", "combined"] as const).map((layer) => <button type="button" key={layer} className={activeLayer === layer ? "active" : ""} onClick={() => setActiveLayer(layer)}>{layer === "buying_center" ? "Buying center" : labelize(layer)}</button>)}</div><div className="ontology-actions"><button type="button" onClick={() => setModal("node")}>＋ Entity</button><button type="button" onClick={() => setModal("edge")}>↗ Connect</button><button type="button" onClick={() => setModal("source")}>↓ Ingest URL</button><button className="needle-action" type="button" onClick={openNeedle}>N Needle enrich</button></div></div>
        <div className="graph-frame"><div className="graph-caption"><span>{activeLayer === "organization" ? "Formal structure and affiliation" : activeLayer === "buying_center" ? "Problem ownership, evaluation, procurement, and entry routes" : "Combined decision ontology"}</span><div>{Object.entries(TYPE_COLORS).slice(0, 7).map(([type, color]) => <i key={type} title={type} style={{ background: color }} />)}</div></div><GraphView graph={visibleGraph} selection={selection} statuses={statuses} onSelect={select} />{busy === "research" && <div className="busy-overlay"><span /><strong>Building evidence graph</strong><small>Discovery → extraction → resolution → ranking</small></div>}</div>

        <section className="results" id="results">
          <div className="results-tabs"><div>{(["stakeholders", "paths", "sources"] as ResultTab[]).map((tab) => <button key={tab} type="button" className={resultTab === tab ? "active" : ""} onClick={() => setResultTab(tab)}>{tab === "stakeholders" ? "Ranked committee" : tab === "paths" ? "Entry routes" : "Evidence ledger"}<b>{tab === "stakeholders" ? graph.stakeholders.length : tab === "paths" ? graph.entryPaths.length : graph.evidence.length}</b></button>)}</div><span>Observed {new Date(graph.createdAt).toLocaleDateString()}</span></div>
          {resultTab === "stakeholders" && <div className="stakeholder-table"><div className="table-head"><span>Candidate</span><span>Why relevant</span><span>Evidence</span><span>Signal</span><span>Score</span></div>{graph.stakeholders.map((candidate, index) => <button type="button" className="table-row" key={candidate.id} onClick={() => select({ kind: "node", id: candidate.nodeId })}><span><i>{String(index + 1).padStart(2, "0")}</i><b>{candidate.label}</b><small>{candidate.role}</small></span><span>{candidate.unknowns[0] ?? candidate.rationale}</span><span>{candidate.evidenceStrength}</span><span>{candidate.buyingSignal}</span><span><em>{candidate.score}</em></span></button>)}</div>}
          {resultTab === "paths" && <div className="path-list">{graph.entryPaths.map((path, index) => <article key={path.id}><span>{String(index + 1).padStart(2, "0")}</span><div><strong>{path.title}</strong><p>{path.summary}</p><div className="route">{path.nodeIds.map((id, pathIndex) => <span key={id}><button type="button" onClick={() => select({ kind: "node", id })}>{graph.nodes.find((node) => node.id === id)?.label ?? id}</button>{pathIndex < path.nodeIds.length - 1 && <b>→</b>}</span>)}</div></div><em className={path.confidence}>{path.confidence}</em></article>)}</div>}
          {resultTab === "sources" && <div className="source-table">{graph.evidence.map((item) => <article key={item.id}><div><span>{item.sourceType}</span>{item.access === "licensed" && <em>LICENSED</em>}</div><strong>{item.title}</strong><p>{item.excerpt}</p><small>{item.observedAt} · {item.provider ?? "Public web"}</small><a href={item.url} target="_blank" rel="noreferrer">Open source ↗</a></article>)}</div>}
        </section>
      </section>

      <aside className="inspector">
        <div className="inspector-top"><span>Inspector</span><span className={`status-chip ${selectedStatus}`}>{selectedStatus}</span></div>
        <div className="entity-summary"><div className="entity-mark" style={{ background: TYPE_COLORS[selectedNode?.type ?? "Evidence"] }}>{selectedNode ? initials(selectedNode.label) : "↗"}</div><span>{selectedNode?.type ?? labelize(selectedEdge?.type ?? "Relationship")}</span><h2>{selectedTitle}</h2><p>{selectedNode?.summary ?? selectedEdge?.rationale ?? "Select an entity or relationship."}</p></div>
        <div className="inspector-tabs">{(["properties", "evidence", "relationships"] as InspectorTab[]).map((tab) => <button type="button" key={tab} className={inspectorTab === tab ? "active" : ""} onClick={() => setInspectorTab(tab)}>{labelize(tab)}</button>)}</div>
        {inspectorTab === "properties" && <div className="inspector-content properties-list"><div><span>Layer</span><strong>{selectedNode?.layers?.map(labelize).join(", ") ?? labelize(selectedEdge?.layer ?? "unassigned")}</strong></div><div><span>Evidence links</span><strong>{selectedEvidence.length}</strong></div>{selectedEdge && <><div><span>Relationship</span><strong>{labelize(selectedEdge.type)}</strong></div><div><span>Confidence</span><strong>{Math.round(selectedEdge.confidence * 100)}%</strong></div></>}<div className="unknown-box"><span>Unknowns</span>{(selectedNode?.unknowns ?? (selectedEdge?.status !== "confirmed" ? ["The public evidence does not explicitly establish this decision relationship."] : ["No explicit unknowns recorded."])).map((unknown) => <p key={unknown}>— {unknown}</p>)}</div><p className="authority-note">A title, profile, or conference appearance never establishes budget or purchasing authority on its own.</p></div>}
        {inspectorTab === "evidence" && <div className="inspector-content inspector-evidence">{selectedEvidence.map((item) => <article key={item.id}><div><span>{item.sourceType}</span><small>{item.observedAt}</small></div><strong>{item.title}</strong><p>{item.excerpt}</p><a href={item.url} target="_blank" rel="noreferrer">View source ↗</a></article>)}{!selectedEvidence.length && <div className="empty-state">No evidence attached. Treat this as a hypothesis.</div>}</div>}
        {inspectorTab === "relationships" && <div className="inspector-content relationship-list">{incidentEdges.map((edge) => { const otherId = edge.source === selectedNode?.id ? edge.target : edge.source; return <button type="button" key={edge.id} onClick={() => select({ kind: "edge", id: edge.id })}><span>{labelize(edge.type)}</span><strong>{graph.nodes.find((node) => node.id === otherId)?.label}</strong><em className={edge.status}>{edge.status}</em></button>; })}{!incidentEdges.length && <div className="empty-state">No relationships for this selection.</div>}</div>}
        <div className="inspector-source"><span>WORKSPACE PROVENANCE</span><strong>{graph.provider}</strong><small>{graph.warnings[0]}</small></div>
      </aside>
    </section>

    {modal === "research" && <ModalFrame eyebrow="LIVE PIPELINE" title="Start a new research run" onClose={() => setModal(null)}><form className="modal-form" onSubmit={runResearch}><label><span>Target enterprise</span><input name="company" defaultValue={graph.company} required /></label><label><span>Startup product description</span><textarea name="product" defaultValue={graph.product} rows={4} required /></label><label><span>Target geography</span><input name="geography" defaultValue={graph.geography} /></label><p className="form-note">This replaces the active workspace after public discovery and conservative extraction. No outreach is sent.</p><button className="submit-button" disabled={busy === "research"}>{busy === "research" ? "Researching…" : "Run research →"}</button></form></ModalFrame>}
    {modal === "node" && <ModalFrame eyebrow="ONTOLOGY EDITOR" title="Add an entity" onClose={() => setModal(null)}><form className="modal-form" onSubmit={addNode}><label><span>Entity type</span><select name="type">{NODE_TYPES.filter((type) => type !== "Evidence").map((type) => <option key={type}>{type}</option>)}</select></label><label><span>Label</span><input name="label" required placeholder="e.g. Warranty analytics team" /></label><label><span>Summary</span><textarea name="summary" rows={3} placeholder="What is known, without overclaiming" /></label><label><span>Graph layer</span><select name="layer"><option value="organization">Organization</option><option value="buying_center">Buying center</option><option value="ecosystem">Ecosystem</option></select></label><p className="form-note">An entity can be added as a research hypothesis. Attach evidence before relying on it.</p><button className="submit-button">Add entity →</button></form></ModalFrame>}
    {modal === "edge" && <ModalFrame eyebrow="ONTOLOGY EDITOR" title="Connect two entities" onClose={() => setModal(null)}><form className="modal-form" onSubmit={addEdge}><div className="form-grid"><label><span>From</span><select name="source">{graph.nodes.map((node) => <option key={node.id} value={node.id}>{node.label}</option>)}</select></label><label><span>To</span><select name="target" defaultValue="aftersales">{graph.nodes.map((node) => <option key={node.id} value={node.id}>{node.label}</option>)}</select></label></div><label><span>Relationship</span><select name="type">{EDGE_TYPES.map((type) => <option key={type}>{type}</option>)}</select></label><div className="form-grid"><label><span>Status</span><select name="status"><option value="confirmed">Confirmed</option><option value="inferred">Inferred</option><option value="uncertain">Uncertain</option></select></label><label><span>Layer</span><select name="layer"><option value="buying_center">Buying center</option><option value="organization">Organization</option><option value="ecosystem">Ecosystem</option></select></label></div><label><span>Confidence <small>0–100</small></span><input name="confidence" type="number" min="0" max="100" defaultValue="70" /></label><label><span>Required source</span><select name="evidenceId" required defaultValue=""><option value="" disabled>Select evidence…</option>{graph.evidence.map((item) => <option key={item.id} value={item.id}>{item.title}</option>)}</select></label><label><span>Rationale</span><textarea name="rationale" rows={3} required placeholder="What the source proves—and what it does not" /></label><button className="submit-button">Create sourced relationship →</button></form></ModalFrame>}
    {modal === "source" && <ModalFrame eyebrow="SOURCE INGESTION" title="Add a public evidence URL" onClose={() => setModal(null)}><form className="modal-form" onSubmit={ingestSource}><label><span>Public URL</span><input name="url" type="url" required placeholder="https://…" /></label><p className="form-note">Enterprise Atlas uses ordinary permitted retrieval, records the observation date, and never bypasses access controls.</p><button className="submit-button" disabled={busy === "source"}>{busy === "source" ? "Retrieving…" : "Ingest source →"}</button></form></ModalFrame>}
    {modal === "needle" && <ModalFrame eyebrow="LICENSED ENRICHMENT" title="Needle LinkedIn research" onClose={() => setModal(null)}><div className="provider-status"><span className={`connection-dot ${needleStatus?.configured ? "connected" : ""}`} /><div><strong>{needleStatus ? needleStatus.configured ? "Read-only adapter ready" : "Adapter not configured" : "Checking connection…"}</strong><p>{needleStatus?.message}</p></div></div><div className="guardrail-list"><span>✓ People and company search only</span><span>✓ Provider provenance on every record</span><span>✓ Exact-match resolution; ambiguity stays separate</span><span>× No messaging, email guessing, or outreach</span></div><label className="cluster-field"><span>Search clusters · one per line</span><textarea rows={6} value={needleKeywords} onChange={(event) => setNeedleKeywords(event.target.value)} /></label>{needleStatus && !needleStatus.configured && <code className="env-code">NEEDLE_API_KEY=…{"\n"}NEEDLE_CONNECTED_ACCOUNT_ID=…</code>}<button className="submit-button" type="button" onClick={runNeedle} disabled={!needleStatus?.configured || busy === "needle"}>{busy === "needle" ? "Enriching…" : "Run licensed enrichment →"}</button></ModalFrame>}
    {modal === "duplicates" && <ModalFrame eyebrow="ENTITY RESOLUTION" title="Review possible duplicates" onClose={() => setModal(null)}>{duplicates.length ? <div className="duplicate-list">{duplicates.map(([left, right]) => <article key={`${left.id}-${right.id}`}><div><span>{left.type}</span><strong>{left.label}</strong></div><b>≈</b><div><span>{right.type}</span><strong>{right.label}</strong></div><button type="button" onClick={() => mergeDuplicate(left, right)}>Merge into first</button></article>)}</div> : <div className="empty-modal"><strong>No merge candidates</strong><p>Enterprise Atlas found no exact label or alias collisions. Ambiguous entities remain separate by design.</p></div>}</ModalFrame>}
  </main>;
}
