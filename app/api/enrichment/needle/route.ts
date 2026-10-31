import { NextResponse } from "next/server";
import { getNeedleStatus, searchNeedlePeople } from "../../../../lib/needle-provider";

export async function GET() {
  return NextResponse.json(getNeedleStatus());
}

export async function POST(request: Request) {
  try {
    const body = await request.json() as { company?: string; keywords?: string[]; geography?: string };
    const company = body.company?.trim();
    const keywords = Array.isArray(body.keywords) ? body.keywords.filter((item) => typeof item === "string" && item.trim()).slice(0, 8) : [];
    if (!company || !keywords.length) return NextResponse.json({ error: "Company and at least one search cluster are required." }, { status: 400 });
    if (!getNeedleStatus().configured) return NextResponse.json({ error: getNeedleStatus().message }, { status: 503 });
    return NextResponse.json(await searchNeedlePeople({ company, keywords, geography: body.geography?.trim() || undefined }));
  } catch (error) {
    return NextResponse.json({ error: error instanceof Error ? error.message : "Needle enrichment failed." }, { status: 502 });
  }
}
