import { EDGE_TYPES, NODE_TYPES, type ExtractedFactSet, type SearchResult } from "./atlas-types";

type ResponseContent = { type?: string; text?: string };
type ResponseItem = { content?: ResponseContent[] };

async function createStructuredResponse(prompt: string, schemaName: string, schema: object, files: string[] = []) {
  const apiKey = process.env.OPENAI_API_KEY;
  if (!apiKey) return null;

  const userContent: Array<Record<string, string>> = [{ type: "input_text", text: prompt }];
  for (const fileUrl of files.slice(0, 4)) userContent.push({ type: "input_file", file_url: fileUrl });

  const response = await fetch("https://api.openai.com/v1/responses", {
    method: "POST",
    headers: { Authorization: `Bearer ${apiKey}`, "content-type": "application/json" },
    body: JSON.stringify({
      model: process.env.OPENAI_MODEL ?? "gpt-5-mini",
      input: [
        {
          role: "system",
          content: [{
            type: "input_text",
            text: "You extract conservative enterprise research facts. Never invent people, employers, reporting lines, responsibilities, emails, authority, budgets, or relationships. Conference appearances prove topic involvement only. Return uncertain or inferred status when the evidence does not make a relationship explicit.",
          }],
        },
        { role: "user", content: userContent },
      ],
      text: { format: { type: "json_schema", name: schemaName, strict: true, schema } },
    }),
    signal: AbortSignal.timeout(55_000),
  });

  if (!response.ok) {
    const body = await response.text();
    throw new Error(`OpenAI extraction failed (${response.status}): ${body.slice(0, 180)}`);
  }
  const data = (await response.json()) as { output_text?: string; output?: ResponseItem[] };
  const text = data.output_text ?? data.output?.flatMap((item) => item.content ?? []).find((item) => item.type === "output_text")?.text;
  if (!text) throw new Error("OpenAI returned no structured output");
  return JSON.parse(text) as unknown;
}

export async function expandProductTerms(product: string): Promise<string[]> {
  const schema = {
    type: "object",
    additionalProperties: false,
    required: ["terms"],
    properties: { terms: { type: "array", minItems: 5, maxItems: 12, items: { type: "string" } } },
  };
  const prompt = `Generate concise business-function, operational-problem, technology, and buying-signal synonyms for this startup product description. Avoid company names. Product: ${product}`;
  const result = (await createStructuredResponse(prompt, "atlas_synonyms", schema)) as { terms?: string[] } | null;
  if (result?.terms?.length) return [...new Set(result.terms.map((term) => term.trim()).filter(Boolean))].slice(0, 12);

  const clean = product.toLowerCase().replace(/[^a-z0-9\s&/-]/g, " ").split(/\s+/).filter((term) => term.length > 3);
  const phrases = [
    product,
    clean.slice(0, 4).join(" "),
    "digital transformation",
    "data analytics",
    "process modernization",
    "implementation partner",
    "supplier procurement",
    "conference presentation",
  ];
  return [...new Set(phrases.filter(Boolean))].slice(0, 10);
}

export async function extractFacts(
  company: string,
  product: string,
  sources: Array<SearchResult & { retrievedText: string }>,
): Promise<ExtractedFactSet | null> {
  if (!process.env.OPENAI_API_KEY) return null;

  const textSources = sources.map((source, index) => [
    `SOURCE_INDEX: ${index}`,
    `TITLE: ${source.title}`,
    `URL: ${source.url}`,
    `CONTENT: ${source.retrievedText.slice(0, 9_000)}`,
  ].join("\n")).join("\n\n---\n\n");

  const schema = {
    type: "object",
    additionalProperties: false,
    required: ["nodes", "edges"],
    properties: {
      nodes: {
        type: "array",
        items: {
          type: "object",
          additionalProperties: false,
          required: ["key", "type", "label", "summary", "aliases", "unknowns", "evidenceIndexes"],
          properties: {
            key: { type: "string" },
            type: { type: "string", enum: NODE_TYPES },
            label: { type: "string" },
            summary: { type: "string" },
            aliases: { type: "array", items: { type: "string" } },
            unknowns: { type: "array", items: { type: "string" } },
            evidenceIndexes: { type: "array", items: { type: "integer", minimum: 0 } },
          },
        },
      },
      edges: {
        type: "array",
        items: {
          type: "object",
          additionalProperties: false,
          required: ["sourceKey", "targetKey", "type", "status", "confidence", "rationale", "evidenceIndexes"],
          properties: {
            sourceKey: { type: "string" },
            targetKey: { type: "string" },
            type: { type: "string", enum: EDGE_TYPES },
            status: { type: "string", enum: ["confirmed", "inferred", "uncertain"] },
            confidence: { type: "number", minimum: 0, maximum: 1 },
            rationale: { type: "string" },
            evidenceIndexes: { type: "array", items: { type: "integer", minimum: 0 } },
          },
        },
      },
    },
  };

  const pdfs = sources.filter((source) => /\.pdf($|\?)/i.test(source.url)).map((source) => source.url);
  const prompt = [
    `Target enterprise: ${company}`,
    `Startup product: ${product}`,
    "Extract only material facts useful for an enterprise buying-center graph.",
    "Every node and edge must cite one or more SOURCE_INDEX values unless it is an explicitly marked inferred hypothesis. Do not infer purchasing authority from titles or appearances. Do not merge ambiguous entities. Use stable short keys. If no relevant facts are supported, return empty arrays.",
    textSources,
  ].join("\n\n");

  return (await createStructuredResponse(prompt, "atlas_fact_extraction", schema, pdfs)) as ExtractedFactSet;
}
