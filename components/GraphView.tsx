"use client";

import cytoscape, { type Core, type ElementDefinition } from "cytoscape";
import { useEffect, useRef } from "react";
import type { ClaimStatus, ResearchGraph } from "../lib/atlas-types";

export type GraphSelection = { kind: "node" | "edge"; id: string };

const colors: Record<string, string> = {
  Company: "#183f31",
  BusinessUnit: "#9ed6ef",
  Function: "#c9f3cf",
  Person: "#f4c7c3",
  Role: "#e3d5f5",
  Project: "#efb17d",
  Technology: "#eedbc4",
  Partner: "#dff467",
  Event: "#f4d37c",
  Tender: "#b8e4da",
  Evidence: "#e2e5df",
};

export function GraphView({
  graph,
  selection,
  statuses,
  onSelect,
}: {
  graph: ResearchGraph;
  selection: GraphSelection | null;
  statuses: Set<ClaimStatus>;
  onSelect: (selection: GraphSelection) => void;
}) {
  const container = useRef<HTMLDivElement>(null);
  const instance = useRef<Core | null>(null);
  const selectCallback = useRef(onSelect);
  selectCallback.current = onSelect;

  useEffect(() => {
    if (!container.current) return;
    const visibleEdges = graph.edges.filter((edge) => statuses.has(edge.status));
    const linkedNodeIds = new Set(visibleEdges.flatMap((edge) => [edge.source, edge.target]));
    const elements: ElementDefinition[] = [
      ...graph.nodes.map((node) => ({
        group: "nodes" as const,
        data: { id: node.id, label: node.label, type: node.type, summary: node.summary, color: colors[node.type] },
      })),
      ...visibleEdges.map((edge) => ({
        group: "edges" as const,
        data: {
          id: edge.id,
          source: edge.source,
          target: edge.target,
          label: edge.type.replaceAll("_", " "),
          status: edge.status,
          confidence: edge.confidence,
        },
      })),
    ];

    instance.current?.destroy();
    const cy = cytoscape({
      container: container.current,
      elements,
      minZoom: 0.35,
      maxZoom: 2.2,
      wheelSensitivity: 0.2,
      style: [
        {
          selector: "node",
          style: {
            width: 128,
            height: 49,
            shape: "round-rectangle",
            "background-color": "data(color)",
            "border-color": "#859189",
            "border-width": 1,
            label: "data(label)",
            color: "#173126",
            "font-family": "Arial, sans-serif",
            "font-size": 10,
            "font-weight": 700,
            "text-wrap": "wrap",
            "text-max-width": 105,
            "text-valign": "center",
            "text-halign": "center",
            "overlay-opacity": 0,
          },
        },
        { selector: 'node[type = "Company"]', style: { color: "#ffffff", "border-color": "#183f31" } },
        { selector: "node:unselected", style: { opacity: (node) => linkedNodeIds.size && !linkedNodeIds.has(node.id()) && graph.edges.length ? 0.72 : 1 } },
        {
          selector: "edge",
          style: {
            width: 1.4,
            "line-color": "#8f9a93",
            "target-arrow-color": "#8f9a93",
            "target-arrow-shape": "triangle",
            "curve-style": "bezier",
            "arrow-scale": 0.7,
            label: "data(label)",
            "font-size": 7,
            "font-family": "Arial, sans-serif",
            color: "#6d7872",
            "text-background-color": "#fafaf7",
            "text-background-opacity": 0.84,
            "text-background-padding": 2,
            "text-rotation": "autorotate",
            "overlay-opacity": 0,
          },
        },
        { selector: 'edge[status = "inferred"]', style: { "line-style": "dashed", "line-color": "#bd9b56", "target-arrow-color": "#bd9b56" } },
        { selector: 'edge[status = "uncertain"]', style: { "line-style": "dotted", "line-color": "#c48161", "target-arrow-color": "#c48161", opacity: 0.78 } },
        { selector: ".selected", style: { "border-width": 3, "border-color": "#163c2e", "line-color": "#163c2e", "target-arrow-color": "#163c2e", "z-index": 99 } },
      ],
      layout: graph.nodes.length > 2
        ? { name: "cose", animate: false, randomize: true, fit: true, padding: 52, nodeRepulsion: () => 270_000, idealEdgeLength: () => 145, gravity: 0.18 }
        : { name: "grid", fit: true, padding: 60 },
    });

    cy.on("tap", "node", (event) => selectCallback.current({ kind: "node", id: event.target.id() }));
    cy.on("tap", "edge", (event) => selectCallback.current({ kind: "edge", id: event.target.id() }));
    instance.current = cy;
    return () => { cy.destroy(); instance.current = null; };
  }, [graph, statuses]);

  useEffect(() => {
    const cy = instance.current;
    if (!cy) return;
    cy.elements().removeClass("selected");
    if (selection) cy.getElementById(selection.id).addClass("selected");
  }, [selection]);

  return (
    <div className="graph-stage">
      <div ref={container} className="cytoscape-canvas" aria-label="Interactive buying-center graph" />
      <div className="zoom-tools" aria-label="Graph zoom controls">
        <button type="button" onClick={() => instance.current?.zoom({ level: Math.min(2.2, (instance.current?.zoom() ?? 1) + 0.18), renderedPosition: { x: 280, y: 220 } })} aria-label="Zoom in">＋</button>
        <button type="button" onClick={() => instance.current?.zoom({ level: Math.max(0.35, (instance.current?.zoom() ?? 1) - 0.18), renderedPosition: { x: 280, y: 220 } })} aria-label="Zoom out">−</button>
        <button type="button" onClick={() => instance.current?.fit(undefined, 42)} aria-label="Fit graph">⌖</button>
      </div>
    </div>
  );
}
