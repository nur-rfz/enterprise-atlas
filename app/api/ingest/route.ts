import { NextResponse } from "next/server";
import { ingestPublicSource } from "../../../lib/source-ingestion";

export async function POST(request: Request) {
  try {
    const body = await request.json() as { url?: string };
    if (!body.url?.trim() || body.url.length > 2_000) return NextResponse.json({ error: "A valid public source URL is required." }, { status: 400 });
    return NextResponse.json(await ingestPublicSource(body.url.trim()));
  } catch (error) {
    return NextResponse.json({ error: error instanceof Error ? error.message : "Source ingestion failed." }, { status: 422 });
  }
}
