"use strict";

const $ = (s, el = document) => el.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
let SNAP = null; // static snapshot (GitHub Pages demo); null when a live API is available
async function liveApi(path, opts) {
  const r = await fetch(path, opts && opts.body ? { method: "POST", headers: { "content-type": "application/json" }, ...opts, body: JSON.stringify(opts.body) } : opts);
  if (!r.ok) throw new Error((await r.text()) || r.status);
  return r.json();
}
function snapApi(path, opts) {
  if (opts && (opts.method === "POST" || opts.body)) throw new Error("This is a read-only published snapshot. Run the engine locally to curate and harvest.");
  const [p, qs] = path.split("?");
  const q = new URLSearchParams(qs || "");
  if (p.startsWith("/api/entity/")) return structuredClone(SNAP.entities[decodeURIComponent(p.slice(12))]);
  if (p === "/api/entities") { const t = (q.get("q") || "").toLowerCase(); return SNAP.search.filter((x) => !t || (x.label + " " + (x.headline || "")).toLowerCase().includes(t)).slice(0, +(q.get("limit") || 30)); }
  if (p === "/api/graph") {
    const min = +(q.get("min_confidence") || 0), L = q.get("layers") ? new Set(q.get("layers").split(",")) : null;
    const edges = SNAP["/api/graph"].edges.filter((e) => e.confidence >= min && (!L || L.has(e.layer)));
    const used = new Set(edges.flatMap((e) => [e.source, e.target]));
    return { nodes: SNAP["/api/graph"].nodes.filter((n) => used.has(n.id)), edges };
  }
  if (p === "/api/committee") { const lim = +(q.get("limit") || 12), c = structuredClone(SNAP[p]); Object.values(c).forEach((b) => (b.top = b.top.slice(0, lim))); return c; }
  if (p === "/api/people") return SNAP[p].slice(0, +(q.get("limit") || 200));
  return structuredClone(SNAP[p]);
}
const api = async (path, opts) => (SNAP ? snapApi(path, opts) : liveApi(path, opts));

const ROLES = {
  business_sponsor: { label: "Business sponsor", hint: "Owns the business outcome", color: "var(--r-sponsor)" },
  problem_owner: { label: "Problem owner", hint: "Runs the process with the pain", color: "var(--r-owner)" },
  evaluator: { label: "Data / analytics evaluator", hint: "Would assess the tool", color: "var(--r-eval)" },
  technical_approver: { label: "IT / architecture", hint: "Approves integration", color: "var(--r-tech)" },
  procurement: { label: "Procurement", hint: "Controls the vendor process", color: "var(--r-proc)" },
  champion: { label: "Champion", hint: "Publicly invested in the topic", color: "var(--r-champ)" },
  introducer: { label: "Introducer", hint: "Partner, alumni or gatekeeper route", color: "var(--r-intro)" },
  user: { label: "End user", hint: "Works with the data daily", color: "var(--r-user)" },
};
const BASIS = {
  self_reported_profile: "LinkedIn profile", official_company: "Official company", procurement_record: "Procurement record",
  event_program: "Event programme", vendor_claim: "Vendor claim", job_ad: "Job ad", association: "Association",
  publication: "Publication", press: "Press", heuristic: "Engine heuristic", analyst: "Analyst",
};
const UNIT = (id) => (id || "").replace(/^(bu|org):/, "").replace(/-/g, " ");
const initials = (s) => s.replace(/\(.*?\)/g, "").split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0]).join("").toUpperCase();

let META = null;
const views = { map, overview, buying, paths, org, graph, evidence, sources };

async function boot() {
  try { if (window.ATLAS_STATIC) throw 0; META = await liveApi("/api/meta"); }
  catch { SNAP = await (await fetch("snapshot.json")).json(); META = SNAP["/api/meta"]; document.body.classList.add("static"); }
  $("#company").textContent = META.company;
  $("#problem").textContent = META.problem.label;
  document.querySelectorAll(".side a").forEach((a) => a.addEventListener("click", () => go(a.dataset.view)));
  $("#drawerClose").onclick = closeDrawer;
  setupSearch();
  go(location.hash.slice(1) || "map");
}

window.addEventListener("hashchange", () => render(location.hash.slice(1)));
function go(view) {
  if (location.hash.slice(1) !== view) location.hash = view; // hashchange renders
  else render(view);
}
function render(view) {
  if (!views[view]) view = "map";
  closeDrawer();
  document.querySelectorAll(".side a").forEach((a) => a.classList.toggle("active", a.dataset.view === view));
  $("#main").innerHTML = '<div class="empty">Loading…</div>';
  views[view]();
}

/* ---------------------------------------------------------------- overview */
async function overview() {
  const [committee, people] = await Promise.all([api("/api/committee?limit=4"), api("/api/people?limit=8")]);
  const st = META.stats;
  const n = (o) => Object.values(o || {}).reduce((a, b) => a + b, 0);
  const ev = st.evidence || {};
  $("#main").innerHTML = `
    <div class="eyebrow">Account map</div>
    <h1>Who decides on ${esc(META.problem.label.toLowerCase())} at Mercedes-Benz</h1>
    <p class="sub">${esc(META.problem.description)} The engine places every person it finds in the organization, then forms buying-role hypotheses from where they sit and what they publicly work on.</p>
    <div class="kpis">
      <div class="kpi"><b>${st.entities.Person || 0}</b><span>people mapped</span></div>
      <div class="kpi"><b>${(st.entities.Team || 0) + (st.entities.Function || 0)}</b><span>functions &amp; teams</span></div>
      <div class="kpi"><b>${(st.entities.BusinessUnit || 0)}</b><span>business units</span></div>
      <div class="kpi"><b>${n(st.evidence)}</b><span>evidence items</span></div>
      <div class="kpi"><b>${n(st.assertions)}</b><span>sourced claims</span></div>
      <div class="kpi"><b>${(ev.job_ad || 0) + (ev.event_program || 0) + (ev.vendor_claim || 0) + (ev.association || 0) + (ev.procurement_record || 0)}</b><span>off-LinkedIn signals</span></div>
    </div>
    <div class="grid2">
      <div class="stack">
        <h2>Buying committee, best candidates</h2>
        <div class="roles">${["business_sponsor", "problem_owner", "evaluator", "technical_approver", "procurement", "champion"].map((r) => roleCard(r, committee[r], 4)).join("")}</div>
      </div>
      <div class="stack">
        <div class="card">
          <h2>Highest-ranked people</h2>
          ${people.map(personRow).join("") || '<div class="empty">No people yet. Run a Needle harvest.</div>'}
        </div>
        <div class="card">
          <h2>Evidence mix</h2>
          ${Object.entries(ev).sort((a, b) => b[1] - a[1]).map(([b, c]) => bar(BASIS[b] || b, c, n(ev))).join("")}
          <p class="fine">LinkedIn tells you where people sit. Job ads, event programmes, vendor case studies, associations and tenders tell you what they actually work on.</p>
        </div>
      </div>
    </div>`;
  bindPeople();
}

const bar = (label, v, max) => `<div class="scorebar"><span>${esc(label)}</span><div class="track"><div class="fill" style="width:${Math.round((100 * v) / Math.max(1, max))}%"></div></div><span class="mono">${v}</span></div>`;

function roleCard(role, block, limit) {
  const R = ROLES[role];
  const top = (block?.top || []).slice(0, limit);
  return `<section class="role"><div class="bar" style="background:${R.color}"></div>
    <header><div><b>${R.label}</b><p>${R.hint}</p></div><span class="n">${block?.count || 0}</span></header>
    ${top.map((p) => personRow(p, role)).join("") || '<div class="empty">No candidate found yet.</div>'}
  </section>`;
}

function personRow(p) {
  const hidden = p.name_visible === false || /name hidden/.test(p.label);
  const s = p.score || 0;
  return `<div class="person" data-id="${esc(p.id)}">
    <div class="av ${hidden ? "hidden" : ""}">${hidden ? "?" : esc(initials(p.label))}</div>
    <div style="min-width:0"><div class="nm">${esc(hidden ? p.title || p.label : p.label)}</div>
      <div class="tt">${esc(hidden ? "Name hidden on LinkedIn · " + UNIT(p.unit) : p.title || "")}${!hidden && p.unit ? " · " + esc(UNIT(p.unit)) : ""}</div></div>
    <span class="score ${s >= 70 ? "hi" : ""}">${s}</span></div>`;
}
const bindPeople = () => document.querySelectorAll("[data-id]").forEach((el) => (el.onclick = (e) => { e.stopPropagation(); openEntity(el.dataset.id); }));

/* ------------------------------------------------------------------ buying */
async function buying() {
  const committee = await api("/api/committee?limit=12");
  $("#main").innerHTML = `
    <div class="eyebrow">Buying-center graph</div>
    <h1>Buying center · ${esc(META.problem.label)}</h1>
    <p class="sub">Purchasing influence does not follow the reporting line. Each column is a role in the deal; people are ranked by problem fit, role strength, evidence and reachability. Open anyone to see exactly which sources support the hypothesis.</p>
    <div class="roles">${Object.keys(ROLES).map((r) => roleCard(r, committee[r], 12)).join("")}</div>`;
  bindPeople();
}

/* --------------------------------------------------------------------- org */
async function org() {
  const tree = await api("/api/org");
  $("#main").innerHTML = `
    <div class="eyebrow">Organizational graph</div>
    <h1>Org map</h1>
    <p class="sub">Company → business unit → function → team, assembled from official sources and corroborated by employee headlines. Confidence rises as independent profiles place people in the same team.</p>
    <div class="tree card">${treeNode(tree, 0)}</div>`;
  document.querySelectorAll(".trow").forEach((r) => {
    r.onclick = (e) => {
      e.stopPropagation();
      if (e.target.classList.contains("tw")) { r.parentElement.querySelector(":scope > .kids")?.toggleAttribute("hidden"); r.querySelector(".tw").textContent = r.parentElement.querySelector(":scope > .kids")?.hidden ? "+" : "−"; }
      else openEntity(r.dataset.eid);
    };
  });
}

function treeNode(t, depth) {
  const units = t.children.filter((c) => c.type !== "Person");
  const people = t.children.filter((c) => c.type === "Person");
  const hasKids = t.children.length > 0;
  const open = depth < 3;
  const status = t.status ? `<span class="status ${t.status}">${t.status} ${Math.round(t.confidence * 100)}%</span>` : "";
  const row = t.type === "Person"
    ? `<div class="trow person" data-eid="${esc(t.id)}"><span class="tw"></span><span class="tl">${esc(t.label)}</span><span class="hc">${t.score || ""}</span></div>`
    : `<div class="trow" data-eid="${esc(t.id)}"><span class="tw">${hasKids ? (open ? "−" : "+") : ""}</span><span class="type">${esc(t.type)}</span><span class="tl">${esc(t.label)}</span>${status}<span class="hc">${t.headcount} people</span></div>`;
  const kids = hasKids ? `<div class="kids tnode" ${open ? "" : "hidden"}>${units.map((u) => treeNode(u, depth + 1)).join("")}${people.map((p) => treeNode(p, depth + 1)).join("")}</div>` : "";
  return `<div>${row}${kids}</div>`;
}

/* ------------------------------------------------------------------- graph */
let cy = null;
const NODE_COLORS = { Company: "#111111", BusinessUnit: "#3d3d3a", Function: "#76746d", Team: "#a8a59c", Person: "#1f3dff", Topic: "#c2255c", Technology: "#0b7285", Partner: "#b4532a", Event: "#7a3cff", Tender: "#5c6b00", Project: "#0f7b4a", Role: "#999" };
async function graph() {
  const state = { layers: new Set(["organization", "buying_center", "ecosystem"]), min: 0.3 };
  $("#main").innerHTML = `
    <div class="eyebrow">Evidence graph</div>
    <h1>Graph</h1>
    <div class="filters" id="gf">
      ${["organization", "buying_center", "ecosystem"].map((l) => `<button class="chip on" data-l="${l}">${l.replace("_", " ")}</button>`).join("")}
      <span class="muted" style="margin-left:12px">min confidence</span>
      ${[0, 0.3, 0.5, 0.7].map((m) => `<button class="chip ${m === 0.3 ? "on" : ""}" data-m="${m}">${m === 0 ? "all" : Math.round(m * 100) + "%"}</button>`).join("")}
    </div>
    <div id="cy"></div>`;
  const draw = async () => {
    const g = await api(`/api/graph?min_confidence=${state.min}&layers=${[...state.layers].join(",")}`);
    if (cy) cy.destroy();
    cy = cytoscape({
      container: $("#cy"),
      elements: [
        ...g.nodes.map((n) => ({ data: { ...n, color: NODE_COLORS[n.type] || "#999", size: n.type === "Company" ? 46 : n.type === "BusinessUnit" ? 32 : n.type === "Person" ? 10 + (n.score || 0) / 6 : 20 } })),
        ...g.edges.map((e) => ({ data: { ...e, w: 0.5 + 2.5 * e.confidence } })),
      ],
      style: [
        { selector: "node", style: { "background-color": "data(color)", width: "data(size)", height: "data(size)", label: "data(label)", "font-size": 9, "font-family": "Inter", color: "#3d3d3a", "text-valign": "bottom", "text-margin-y": 4, "text-max-width": 120, "text-wrap": "ellipsis" } },
        { selector: "node[type='Person']", style: { label: "" } },
        { selector: "node:selected, node.hl", style: { "border-width": 3, "border-color": "#111", label: "data(label)" } },
        { selector: "edge", style: { width: "data(w)", "line-color": "#d9d6cc", "curve-style": "bezier", "target-arrow-shape": "triangle", "target-arrow-color": "#d9d6cc", "arrow-scale": 0.6 } },
        { selector: "edge[status='confirmed']", style: { "line-color": "#9fc9b3", "target-arrow-color": "#9fc9b3" } },
        { selector: "edge[status='inferred']", style: { "line-style": "dashed" } },
        { selector: "edge[status='uncertain']", style: { "line-style": "dotted" } },
        { selector: "edge[layer='buying_center']", style: { "line-color": "#c9cff9", "target-arrow-color": "#c9cff9" } },
      ],
      layout: { name: "cose", animate: false, nodeRepulsion: 9000, idealEdgeLength: 70, padding: 20 },
      wheelSensitivity: 0.2,
    });
    cy.on("tap", "node", (e) => openEntity(e.target.id()));
    cy.on("mouseover", "node", (e) => e.target.addClass("hl"));
    cy.on("mouseout", "node", (e) => e.target.removeClass("hl"));
  };
  $("#gf").onclick = (e) => {
    const b = e.target.closest("button"); if (!b) return;
    if (b.dataset.l) { b.classList.toggle("on"); state.layers.has(b.dataset.l) ? state.layers.delete(b.dataset.l) : state.layers.add(b.dataset.l); }
    if (b.dataset.m) { state.min = +b.dataset.m; document.querySelectorAll("[data-m]").forEach((x) => x.classList.toggle("on", x === b)); }
    draw();
  };
  draw();
}

/* ---------------------------------------------------------------- evidence */
async function evidence() {
  const rows = await api("/api/evidence");
  const bases = [...new Set(rows.map((r) => r.basis))];
  let filter = null;
  const render = () => {
    const list = rows.filter((r) => !filter || r.basis === filter);
    $("#evt").innerHTML = list.map((r) => `<tr>
      <td><span class="tag basis">${esc(BASIS[r.basis] || r.basis)}</span></td>
      <td><a href="${esc(r.url)}" target="_blank" rel="noopener">${esc(r.title)}</a><div class="muted" style="font-size:12px">${esc(r.excerpt).slice(0, 220)}</div></td>
      <td class="mono">${esc(r.provider)}${r.access === "licensed" ? " · licensed" : ""}</td>
      <td class="mono">${esc(r.observed_at)}</td><td class="mono">${r.claims}</td></tr>`).join("");
  };
  $("#main").innerHTML = `
    <div class="eyebrow">Evidence ledger</div>
    <h1>Evidence</h1>
    <p class="sub">Every claim in the graph points to one of these. Licensed LinkedIn data is marked; search summaries are flagged as non-verbatim until the page is fetched.</p>
    <div class="filters" id="ef"><button class="chip on" data-b="">All · ${rows.length}</button>${bases.map((b) => `<button class="chip" data-b="${b}">${esc(BASIS[b] || b)} · ${rows.filter((r) => r.basis === b).length}</button>`).join("")}</div>
    <table><thead><tr><th>Basis</th><th>Source</th><th>Provider</th><th>Observed</th><th>Claims</th></tr></thead><tbody id="evt"></tbody></table>`;
  $("#ef").onclick = (e) => { const b = e.target.closest("button"); if (!b) return; filter = b.dataset.b || null; document.querySelectorAll("#ef .chip").forEach((x) => x.classList.toggle("on", x === b)); render(); };
  render();
}

/* ----------------------------------------------------------------- sources */
async function sources() {
  const s = await api("/api/sources");
  const rows = [
    ["needle.people_search", "LinkedIn people (Needle)", "Org placement, titles, seniority. ~100 searches/day on a standard account."],
    ["web.page", "Web pages", "Event programmes, job ads, vendor case studies, associations."],
    ["llm.extraction", "Claude extraction cache", "Structured claims extracted from fetched pages."],
    ["ted.search", "TED EU tenders", "Buyers, winners, notices. Mercedes-Benz shows up mostly as a supplier."],
    ["vergabe.ocds", "German procurement (OCDS)", "oeffentlichevergabe.de daily exports."],
  ];
  $("#main").innerHTML = `
    <div class="eyebrow">Collectors</div>
    <h1>Sources</h1>
    <p class="sub">Raw responses are stored verbatim. The graph is rebuilt deterministically from them, so improving a parser upgrades every past harvest.</p>
    <table><thead><tr><th>Collector</th><th>What it gives</th><th>Documents</th><th>Last run</th></tr></thead><tbody>
      ${rows.map(([k, n, d]) => `<tr><td><b>${n}</b><div class="mono muted">${k}</div></td><td>${d}</td><td class="mono">${s.collected[k]?.documents || 0}</td><td class="mono">${(s.collected[k]?.last || "—").slice(0, 16)}</td></tr>`).join("")}
    </tbody></table>
    <div class="actions" style="margin-top:18px">
      <button class="btn dark" id="hn" ${s.configured.needle ? "" : "disabled title='Set NEEDLE_API_KEY'"}>Harvest LinkedIn via Needle</button>
      <button class="btn" id="iu">Ingest URLs…</button>
      <button class="btn" id="rb">Rebuild graph</button>
    </div>
    ${s.configured.needle ? "" : '<div class="note">NEEDLE_API_KEY is not set on the server, so live LinkedIn harvesting is off. Existing harvests are still shown.</div>'}
    ${s.configured.anthropic ? "" : '<div class="note">ANTHROPIC_API_KEY is not set, so fetched pages are stored but not yet turned into claims.</div>'}
    <pre id="out" class="mono muted"></pre>`;
  const out = (x) => ($("#out").textContent = JSON.stringify(x, null, 2));
  $("#rb").onclick = async () => out(await api("/api/rebuild", { method: "POST" }));
  $("#hn").onclick = async () => { out("Harvesting…"); out(await api("/api/harvest/needle", { method: "POST" })); };
  $("#iu").onclick = () => form("Ingest URLs", [{ name: "urls", label: "One URL per line", textarea: true }], async (v) => out(await api("/api/ingest/urls", { body: { urls: v.urls.split(/\s+/).filter(Boolean) } })));
}

/* -------------------------------------------------------------- decision map */
const ROLE_ORDER = ["business_sponsor", "problem_owner", "evaluator", "technical_approver", "procurement", "champion", "introducer"];
const OWNER_FN = /after-sales|warranty|quality|field|customer service/i;

async function map() {
  const [tree, committee, paths, signals] = await Promise.all([api("/api/org"), api("/api/committee?limit=25"), api("/api/paths"), api("/api/signals")]);
  // index the tree: parent links + role weight per subtree
  const parent = {}, nodes = {};
  const roleOf = {};
  ROLE_ORDER.forEach((r) => committee[r].top.forEach((p) => { (roleOf[p.id] ||= []).push({ role: r, ...p }); }));
  (function walk(n, par) { nodes[n.id] = n; if (par) parent[n.id] = par; n.children.forEach((c) => walk(c, n.id)); })(tree, null);
  const weight = (n) => (n.type === "Person" ? (roleOf[n.id] || []).reduce((a, r) => a + r.confidence * (r.score || 0) / 100, 0) : n.children.reduce((a, c) => a + weight(c), 0));
  const unitsOf = (n) => n.children.filter((c) => c.type === "BusinessUnit" || c.type === "Company");
  const allUnits = [];
  (function collect(n) { unitsOf(n).forEach((u) => { allUnits.push(u); collect(u); }); })(tree);
  allUnits.forEach((u) => (u.w = weight(u)));
  allUnits.sort((a, b) => b.w - a.w);
  const units = allUnits.filter((u) => u.headcount > 0).slice(0, 7);
  const maxW = Math.max(...units.map((u) => u.w), 0.01);
  // target teams: functions/teams in the problem domain, ranked by weight
  const teams = [];
  (function collectTeams(n) { n.children.forEach((c) => { if (c.type === "Function" || c.type === "Team") { c.w = weight(c); if (c.w > 0 && (OWNER_FN.test(c.label) || c.type === "Team")) teams.push(c); } if (c.type !== "Person") collectTeams(c); }); })(tree);
  teams.sort((a, b) => b.w - a.w);
  const shownTeams = teams.filter((t) => !(t.type === "Function" && teams.some((x) => x !== t && parent[x.id] === t.id && x.w >= t.w * 0.6))).slice(0, 8);
  const unitOfNode = (id) => { let x = id; while (x && nodes[x] && nodes[x].type !== "BusinessUnit" && nodes[x].type !== "Company") x = parent[x]; return x; };
  const teamOfPerson = (id) => { let x = parent[id]; while (x) { if (shownTeams.some((t) => t.id === x)) return x; x = parent[x]; } return null; };
  const PREFER = { procurement: /software|\bit\b/i, technical_approver: /after ?sales|warranty/i };
  const bestPerRole = ROLE_ORDER.map((r) => {
    let cands = committee[r].top.slice().sort((a, b) => b.confidence * b.score - a.confidence * a.score);
    const pref = PREFER[r] && cands.filter((p) => PREFER[r].test(p.title || p.label));
    if (pref && pref.length) cands = pref;
    return { role: r, p: cands[0], n: committee[r].count };
  });
  const relevance = (w) => (w / maxW > 0.45 ? ["target", "Target domain"] : w / maxW > 0.1 ? ["adjacent", "Adjacent"] : ["low", "Low relevance"]);

  $("#main").innerHTML = `
    <div class="hero">
      <div>
        <div class="eyebrow">Decision map · ${esc(META.company)}</div>
        <h1>Who actually decides on <em>${esc(META.problem.label.toLowerCase())}</em></h1>
        <p class="sub">Not the org chart, but the buying center around one problem. Built from ${META.stats.entities.Person || 0} real people and ${Object.values(META.stats.evidence || {}).reduce((a, b) => a + b, 0)} sourced evidence items. Every line carries a source, a date and a confidence.</p>
      </div>
      <div class="hero-stats">
        <div><b>${META.stats.entities.Person || 0}</b><span>people placed</span></div>
        <div><b>${(META.stats.entities.Team || 0) + (META.stats.entities.Function || 0)}</b><span>teams found</span></div>
        <div><b>${signals.length}</b><span>hidden signals</span></div>
      </div>
    </div>
    <div class="dmap" id="dmap">
      <svg class="wires" id="wires"></svg>
      <div class="dcol"><div class="colh">Company</div>
        <div class="dnode company" data-k="${esc(tree.id)}" data-id="${esc(tree.id)}"><b>${esc(tree.label)}</b><span>${tree.headcount} mapped</span></div></div>
      <div class="dcol"><div class="colh">Business units</div>
        ${units.map((u) => { const [cls, txt] = relevance(u.w); return `<div class="dnode unit ${cls}" data-k="${esc(u.id)}" data-par="${esc(parent[u.id] && units.some((x) => x.id === parent[u.id]) ? parent[u.id] : tree.id)}" data-id="${esc(u.id)}"><b>${esc(u.label)}</b><span class="relv ${cls}">${txt}</span><i style="width:${Math.round(100 * u.w / maxW)}%"></i></div>`; }).join("")}</div>
      <div class="dcol"><div class="colh">Where the problem lives</div>
        ${shownTeams.map((t) => `<div class="dnode team" data-k="${esc(t.id)}" data-par="${esc(unitOfNode(t.id))}" data-id="${esc(t.id)}"><b>${esc(t.label)}</b><span>${esc(nodes[unitOfNode(t.id)]?.label || "")} · ${t.headcount} people</span></div>`).join("")}</div>
      <div class="dcol roles-col"><div class="colh">Buying roles</div>
        ${bestPerRole.map(({ role, p, n }) => p ? `<div class="dnode prole" data-k="${esc(p.id)}" data-par="${esc(teamOfPerson(p.id) || unitOfNode(p.id) || "")}" data-id="${esc(p.id)}" style="--rc:${ROLES[role].color}">
            <div class="rname">${esc(ROLES[role].label)} <small>${n}</small></div>
            <b>${esc(p.name_visible === false ? p.title : p.label)}</b>
            <span>${esc(p.name_visible === false ? "Name hidden · " : "")}${esc((p.title || "").slice(0, 70))}</span>
            <div class="rconf"><i style="width:${Math.round(p.confidence * 100)}%"></i><em>${Math.round(p.confidence * 100)}% role · rank ${p.score}</em></div></div>`
          : `<div class="dnode prole empty-role" style="--rc:${ROLES[role].color}"><div class="rname">${esc(ROLES[role].label)}</div><span>No candidate yet. Harvest more.</span></div>`).join("")}</div>
    </div>
    <p class="fine" style="margin-top:10px">Roles are hypotheses from where people sit and what they publicly work on. Seniority alone never makes a sponsor. Open any card for the sources.</p>
    <div class="grid2" style="margin-top:28px">
      <div><h2>Entry paths</h2>${paths.map(pathCard).join("")}</div>
      <div><h2>Hidden signals <span class="muted">· beyond LinkedIn</span></h2>${signals.slice(0, 8).map(signalRow).join("")}</div>
    </div>`;
  bindPeople();
  requestAnimationFrame(drawWires);
  window.onresize = () => $("#wires") && drawWires();
}

function drawWires() {
  const box = $("#dmap"), svg = $("#wires");
  if (!box || !svg) return;
  const b = box.getBoundingClientRect();
  svg.setAttribute("width", b.width); svg.setAttribute("height", b.height);
  const pos = {};
  box.querySelectorAll(".dnode[data-k]").forEach((el) => { const r = el.getBoundingClientRect(); pos[el.dataset.k] = { l: r.left - b.left, r: r.right - b.left, y: r.top - b.top + r.height / 2 }; });
  let d = "";
  box.querySelectorAll(".dnode[data-par]").forEach((el) => {
    const a = pos[el.dataset.par], z = pos[el.dataset.k];
    if (!a || !z || a.r >= z.l) return;
    const mx = (a.r + z.l) / 2;
    d += `<path d="M${a.r},${a.y} C${mx},${a.y} ${mx},${z.y} ${z.l},${z.y}" class="${el.classList.contains("prole") ? "wp" : ""}" style="${el.classList.contains("prole") ? `stroke:${getComputedStyle(el).getPropertyValue("--rc")}` : ""}"/>`;
  });
  svg.innerHTML = d;
}

function pathCard(p) {
  return `<div class="pathcard ${p.kind}"><div class="ph"><b>${esc(p.title)}</b></div><p>${esc(p.why)}</p>
    <ol>${p.steps.map((s) => `<li data-id="${esc(s.id)}"><span class="dotr" style="background:${ROLES[s.role].color}"></span><div><b>${esc(/name hidden/.test(s.label) ? s.title : s.label)}</b><small>${esc(ROLES[s.role].label)}${/name hidden/.test(s.label) ? " · name hidden" : " · " + esc((s.title || "").slice(0, 60))}</small></div></li>`).join("")}</ol></div>`;
}

function signalRow(s) {
  return `<a class="signal" href="${esc(s.url)}" target="_blank" rel="noopener"><span class="tag basis">${esc(BASIS[s.basis] || s.basis)}</span>
    <div><b>${esc(s.title)}</b><small>${esc((s.excerpt || "").slice(0, 150))}</small></div><em>${s.claims} claims</em></a>`;
}

async function paths() {
  const [ps, signals] = await Promise.all([api("/api/paths"), api("/api/signals")]);
  $("#main").innerHTML = `
    <div class="eyebrow">Go-to-market</div>
    <h1>Entry paths</h1>
    <p class="sub">Four ways into the buying center. Each step is a real, ranked person with the evidence for their role. Pick the route that matches your proof points.</p>
    <div class="paths-grid">${ps.map(pathCard).join("")}</div>
    <h2 style="margin-top:28px">All hidden signals</h2>${signals.map(signalRow).join("")}`;
  bindPeople();
}

/* ------------------------------------------------------------------ drawer */
async function openEntity(id) {
  const d = await api(`/api/entity/${encodeURIComponent(id)}`);
  const e = d.entity, p = e.props || {};
  const sc = p.scores;
  const roles = p.buying_roles || [];
  $("#drawerBody").innerHTML = `
    <div class="eyebrow">${esc(e.type)}</div>
    <h1>${esc(e.label)}</h1>
    ${p.headline ? `<div class="muted">${esc(p.headline)}</div>` : ""}
    <div style="margin-top:8px">${roles.map((r) => `<span class="tag rtag" style="background:${ROLES[r.role]?.color}">${esc(ROLES[r.role]?.label || r.role)} · ${Math.round(r.confidence * 100)}%</span>`).join("")}</div>
    <dl class="kv">
      ${p.unit ? `<dt>Unit</dt><dd>${esc(UNIT(p.unit))}</dd>` : ""}
      ${p.seniority ? `<dt>Seniority</dt><dd>${esc(p.seniority)}</dd>` : ""}
      ${p.functions?.length ? `<dt>Functions</dt><dd>${[...new Set([...p.functions, ...(p.subfunctions || [])])].map((f) => `<span class="tag">${esc(f.replace(/_/g, " "))}</span>`).join("")}</dd>` : ""}
      ${p.location ? `<dt>Location</dt><dd>${esc(p.location)}</dd>` : ""}
      ${p.degree ? `<dt>Network</dt><dd>${esc(p.degree.replace(/_/g, " "))}</dd>` : ""}
      ${p.profile_url ? `<dt>Profile</dt><dd><a href="${esc(p.profile_url)}" target="_blank" rel="noopener">LinkedIn ↗</a></dd>` : ""}
      ${p.description ? `<dt>About</dt><dd>${esc(p.description)}</dd>` : ""}
    </dl>
    ${(p.notes || []).map((n) => `<div class="note">${esc(n)}</div>`).join("")}
    ${sc && sc.score ? `<h2>Why this rank · ${sc.score}</h2>${bar("Problem fit", sc.problem_fit, 100)}${bar("Role strength", sc.role_strength, 100)}${bar("Evidence", sc.evidence, 100)}${bar("Reachability", sc.reachability, 100)}${sc.activity ? bar("Public activity", sc.activity, 100) : ""}` : ""}
    ${roles.map((r) => `<p class="fine"><b>${esc(ROLES[r.role]?.label || r.role)}:</b> ${esc(r.rationale)}</p>`).join("")}
    <div class="actions">
      <button class="btn" id="addRel">Add relationship</button>
      <button class="btn" id="mergeE">Merge into…</button>
    </div>
    <h2>Relationships · ${d.relationships.length}</h2>
    ${d.relationships.map((r) => relCard(r, id)).join("") || '<div class="empty">No relationships.</div>'}`;
  $("#drawer").classList.add("open");
  document.querySelectorAll(".rel > header").forEach((h) => (h.onclick = () => h.parentElement.classList.toggle("open")));
  document.querySelectorAll("[data-goto]").forEach((a) => (a.onclick = (ev) => { ev.stopPropagation(); openEntity(a.dataset.goto); }));
  document.querySelectorAll("[data-reject]").forEach((b) => (b.onclick = async (ev) => {
    ev.stopPropagation();
    const reason = prompt("Why is this claim wrong?"); if (reason === null) return;
    await api(`/api/assertions/${encodeURIComponent(b.dataset.reject)}/reject`, { body: { reason } }); openEntity(id);
  }));
  $("#addRel").onclick = () => form("Add relationship", [
    { name: "type", label: "Relationship", options: META.edge_types },
    { name: "dst", label: "Target (search)", entity: true },
    { name: "basis", label: "Basis", options: META.bases.filter((b) => b !== "heuristic") },
    { name: "url", label: "Source URL (required unless basis = analyst)" },
    { name: "note", label: "Quote or note", textarea: true },
    { name: "confidence", label: "Confidence (0–1)", value: "0.7" },
  ], async (v) => { await api("/api/assertions", { body: { src: id, dst: v.dst, type: v.type, basis: v.basis, url: v.url || null, note: v.note, confidence: +v.confidence } }); openEntity(id); });
  $("#mergeE").onclick = () => form(`Merge “${e.label}” into…`, [{ name: "dst", label: "Keep this entity", entity: true }], async (v) => { await api("/api/merge", { body: { src: id, dst: v.dst } }); openEntity(v.dst); });
}

function relCard(r, self) {
  const out = r.source === self;
  const other = out ? r.target : r.source, otherLabel = out ? r.target_label : r.source_label;
  return `<div class="rel"><header>
      <span class="rt">${out ? "" : "← "}${esc(r.type)}${out ? " →" : ""}</span>
      <a data-goto="${esc(other)}" style="cursor:pointer;font-weight:550">${esc(otherLabel)}</a>
      <span class="status ${r.status}">${r.status}</span>
      <span class="conf">${Math.round(r.confidence * 100)}% · ${r.n} src</span>
    </header>
    <div class="claims">${r.assertions.map((a) => `<div class="claim">
      <div class="meta"><span class="tag basis">${esc(BASIS[a.basis] || a.basis)}</span><span>${Math.round(a.confidence * 100)}%</span><span>observed ${esc(a.observed_at)}</span>
        ${a.evidence ? `<a href="${esc(a.evidence.url)}" target="_blank" rel="noopener">${esc(a.evidence.provider)} ↗</a>` : ""}
        <button class="btn small" data-reject="${esc(a.id)}" style="margin-left:auto">Reject</button></div>
      <q>${esc(a.rationale || a.evidence?.excerpt || "")}</q></div>`).join("")}</div></div>`;
}
const closeDrawer = () => $("#drawer").classList.remove("open");

/* ------------------------------------------------------------------- forms */
function form(title, fields, onSubmit) {
  const dlg = $("#dlg");
  $("#dlgForm").innerHTML = `<h2>${esc(title)}</h2>${fields.map((f) => `<label>${esc(f.label)}</label>${
    f.options ? `<select name="${f.name}">${f.options.map((o) => `<option>${esc(o)}</option>`).join("")}</select>`
    : f.textarea ? `<textarea name="${f.name}" rows="3"></textarea>`
    : f.entity ? `<input name="${f.name}_q" placeholder="type to search" autocomplete="off"/><input type="hidden" name="${f.name}"/><div class="results" style="position:static"></div>`
    : `<input name="${f.name}" value="${esc(f.value || "")}"/>`}`).join("")}
    <div class="actions" style="justify-content:flex-end"><button class="btn" value="cancel">Cancel</button><button class="btn dark" value="ok">Save</button></div>`;
  fields.filter((f) => f.entity).forEach((f) => {
    const q = $(`[name="${f.name}_q"]`, dlg), hid = $(`[name="${f.name}"]`, dlg), res = q.nextElementSibling.nextElementSibling;
    q.oninput = async () => {
      const list = await api(`/api/entities?q=${encodeURIComponent(q.value)}&limit=8`);
      res.classList.add("open");
      res.innerHTML = list.map((x) => `<div data-v="${esc(x.id)}">${esc(x.label)}<small>${esc(x.type)}</small></div>`).join("");
      res.querySelectorAll("div").forEach((d) => (d.onclick = () => { hid.value = d.dataset.v; q.value = d.textContent; res.classList.remove("open"); }));
    };
  });
  dlg.onclose = async () => {
    if (dlg.returnValue !== "ok") return;
    const v = Object.fromEntries(new FormData($("#dlgForm")).entries());
    try { await onSubmit(v); } catch (err) { alert(err.message); }
  };
  dlg.showModal();
}

/* ------------------------------------------------------------------ search */
function setupSearch() {
  const q = $("#q"), res = $("#qres");
  let t;
  q.oninput = () => {
    clearTimeout(t);
    t = setTimeout(async () => {
      if (!q.value.trim()) return res.classList.remove("open");
      const list = await api(`/api/entities?q=${encodeURIComponent(q.value)}&limit=12`);
      res.innerHTML = list.map((x) => `<div data-v="${esc(x.id)}">${esc(x.label)}<small>${esc(x.type)}</small></div>`).join("") || '<div class="muted">No match</div>';
      res.classList.add("open");
      res.querySelectorAll("[data-v]").forEach((d) => (d.onclick = () => { res.classList.remove("open"); openEntity(d.dataset.v); }));
    }, 150);
  };
  document.addEventListener("click", (e) => { if (!e.target.closest(".search")) res.classList.remove("open"); });
}

boot();
