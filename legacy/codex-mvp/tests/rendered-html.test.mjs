import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

async function getWorker() {
  const workerUrl = new URL("../dist/server/index.js", import.meta.url);
  workerUrl.searchParams.set("test", `${process.pid}-${Date.now()}`);
  return (await import(workerUrl.href)).default;
}

const environment = {
  ASSETS: { fetch: async () => new Response("Not found", { status: 404 }) },
};
const context = { waitUntil() {}, passThroughOnException() {} };

test("server-renders the Enterprise Atlas workspace", async () => {
  const worker = await getWorker();
  const response = await worker.fetch(new Request("http://localhost/", { headers: { accept: "text/html" } }), environment, context);
  assert.equal(response.status, 200);
  assert.match(response.headers.get("content-type") ?? "", /^text\/html\b/i);
  const html = await response.text();
  assert.match(html, /<title>Enterprise Atlas — Buying-center intelligence<\/title>/i);
  assert.match(html, /Evidence workspace/);
  assert.match(html, /Mercedes-Benz Group/);
  assert.match(html, /Combined decision ontology/);
  assert.match(html, /Ranked committee/);
  assert.match(html, /never establishes budget or purchasing authority/i);
  assert.doesNotMatch(html, /codex-preview|react-loading-skeleton|Your site is taking shape/);
});

test("research API validates required inputs", async () => {
  const worker = await getWorker();
  const response = await worker.fetch(new Request("http://localhost/api/research", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ company: "", product: "" }),
  }), environment, context);
  assert.equal(response.status, 400);
  assert.match(await response.text(), /required/i);
});

test("Mercedes snapshot and pipeline preserve evidence guardrails", async () => {
  const [fixture, pipeline, extractor, needle] = await Promise.all([
    readFile(new URL("../lib/mercedes-graph.ts", import.meta.url), "utf8"),
    readFile(new URL("../lib/research-pipeline.ts", import.meta.url), "utf8"),
    readFile(new URL("../lib/openai-extraction.ts", import.meta.url), "utf8"),
    readFile(new URL("../lib/needle-provider.ts", import.meta.url), "utf8"),
  ]);
  assert.match(fixture, /illustrative:\s*false/);
  assert.match(fixture, /budget authority/i);
  assert.match(fixture, /https:\/\/group\.mercedes-benz\.com\/company\/suppliers\//);
  assert.match(pipeline, /status === "confirmed" && evidenceIds\.length === 0/);
  assert.match(extractor, /Never invent people/);
  assert.match(extractor, /Do not infer purchasing authority/);
  assert.match(needle, /read-only LinkedIn enrichment/i);
  assert.doesNotMatch(needle, /\/messages|send-message|send-inmail/i);
});
