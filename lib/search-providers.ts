import type { SearchResult, SourceType } from "./atlas-types";

export interface WebSearchProvider {
  name: string;
  search(query: string, limit: number): Promise<SearchResult[]>;
}

function classifySource(url: string, title = ""): SourceType {
  const haystack = `${url} ${title}`.toLowerCase();
  if (/jobs?|careers?|vacan/.test(haystack)) return "job";
  if (/conference|summit|agenda|speaker|webinar|event/.test(haystack)) return "event";
  if (/tender|procure|supplier|contract|ted\.europa/.test(haystack)) return "tender";
  if (/partner|case-study|customer-story|implementation/.test(haystack)) return "partner";
  if (/association|working-group|standards|consortium/.test(haystack)) return "association";
  if (/research|paper|journal|publication/.test(haystack)) return "research";
  return "company";
}

class TavilySearchProvider implements WebSearchProvider {
  name = "Tavily";

  constructor(private apiKey: string) {}

  async search(query: string, limit: number): Promise<SearchResult[]> {
    const response = await fetch("https://api.tavily.com/search", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        api_key: this.apiKey,
        query,
        topic: "general",
        search_depth: "advanced",
        max_results: limit,
        include_raw_content: "markdown",
        include_answer: false,
      }),
      signal: AbortSignal.timeout(20_000),
    });
    if (!response.ok) throw new Error(`Tavily search failed (${response.status})`);
    const data = (await response.json()) as {
      results?: Array<{ url: string; title: string; content?: string; raw_content?: string; published_date?: string }>;
    };
    return (data.results ?? []).map((item) => ({
      url: item.url,
      title: item.title,
      snippet: item.content ?? "",
      rawContent: item.raw_content,
      publishedAt: item.published_date,
      sourceType: classifySource(item.url, item.title),
    }));
  }
}

class BraveSearchProvider implements WebSearchProvider {
  name = "Brave Search";

  constructor(private apiKey: string) {}

  async search(query: string, limit: number): Promise<SearchResult[]> {
    const url = new URL("https://api.search.brave.com/res/v1/web/search");
    url.searchParams.set("q", query);
    url.searchParams.set("count", String(limit));
    url.searchParams.set("safesearch", "moderate");
    const response = await fetch(url, {
      headers: { Accept: "application/json", "X-Subscription-Token": this.apiKey },
      signal: AbortSignal.timeout(20_000),
    });
    if (!response.ok) throw new Error(`Brave search failed (${response.status})`);
    const data = (await response.json()) as {
      web?: { results?: Array<{ url: string; title: string; description?: string; age?: string }> };
    };
    return (data.web?.results ?? []).map((item) => ({
      url: item.url,
      title: item.title,
      snippet: item.description ?? "",
      publishedAt: item.age,
      sourceType: classifySource(item.url, item.title),
    }));
  }
}

export function getSearchProvider(): WebSearchProvider | null {
  const preference = (process.env.SEARCH_PROVIDER ?? "").toLowerCase();
  if ((preference === "tavily" || (!preference && process.env.TAVILY_API_KEY)) && process.env.TAVILY_API_KEY) {
    return new TavilySearchProvider(process.env.TAVILY_API_KEY);
  }
  if ((preference === "brave" || (!preference && process.env.BRAVE_SEARCH_API_KEY)) && process.env.BRAVE_SEARCH_API_KEY) {
    return new BraveSearchProvider(process.env.BRAVE_SEARCH_API_KEY);
  }
  return null;
}
