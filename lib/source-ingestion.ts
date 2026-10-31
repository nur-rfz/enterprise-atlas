import type { AtlasEvidence, SourceType } from "./atlas-types";

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
    .trim());
}

function classify(url: string, title: string): SourceType {
  const value = `${url} ${title}`.toLowerCase();
  if (/job|career|vacan/.test(value)) return "job";
  if (/event|conference|speaker|agenda|summit|webinar/.test(value)) return "event";
  if (/tender|procure|supplier|contract|ted\.europa/.test(value)) return "tender";
  if (/partner|case.?study|customer.?story/.test(value)) return "partner";
  if (/association|working.?group|consortium|standard/.test(value)) return "association";
  if (/research|paper|journal|publication/.test(value)) return "research";
  return "company";
}

function assertPublicUrl(input: string) {
  const url = new URL(input);
  if (!/^https?:$/.test(url.protocol)) throw new Error("Only public HTTP and HTTPS URLs can be ingested.");
  const host = url.hostname.toLowerCase();
  if (host === "localhost" || host.endsWith(".local") || host === "0.0.0.0" || host === "127.0.0.1" || host === "::1" || /^(10\.|192\.168\.|169\.254\.|172\.(1[6-9]|2\d|3[01])\.)/.test(host)) {
    throw new Error("Private-network URLs cannot be ingested.");
  }
  return url;
}

export async function ingestPublicSource(input: string): Promise<AtlasEvidence> {
  const url = assertPublicUrl(input);
  const response = await fetch(url, {
    headers: { "user-agent": "EnterpriseAtlas/0.2 (+public research; respects access controls)", Accept: "text/html,application/xhtml+xml,application/pdf,text/plain" },
    redirect: "follow",
    signal: AbortSignal.timeout(15_000),
  });
  if (!response.ok) throw new Error(`The source returned HTTP ${response.status}.`);
  const type = response.headers.get("content-type") ?? "";
  const observedAt = new Date().toISOString().slice(0, 10);
  const id = `source-${Date.now().toString(36)}`;
  if (type.includes("pdf") || /\.pdf$/i.test(url.pathname)) {
    return { id, url: url.toString(), title: url.pathname.split("/").pop() || "Public PDF", excerpt: "Public PDF recorded for structured extraction and manual evidence review.", locator: "PDF URL", observedAt, sourceType: classify(url.toString(), "PDF"), available: true, provider: "Direct retrieval", access: "public" };
  }
  if (!type.includes("html") && !type.includes("text")) throw new Error(`Unsupported source content type: ${type || "unknown"}.`);
  const html = (await response.text()).slice(0, 1_500_000);
  const rawTitle = html.match(/<title[^>]*>([\s\S]*?)<\/title>/i)?.[1] ?? url.hostname;
  const title = htmlToText(rawTitle).slice(0, 180) || url.hostname;
  const content = htmlToText(html);
  return { id, url: url.toString(), title, excerpt: content.slice(0, 520), locator: "Retrieved page text", observedAt, sourceType: classify(url.toString(), title), available: true, provider: "Direct retrieval", access: "public" };
}
