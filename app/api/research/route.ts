import { NextResponse } from "next/server";
import type { ResearchRequest } from "../../../lib/atlas-types";
import { runResearch } from "../../../lib/research-pipeline";

export async function POST(request: Request) {
  try {
    const body = (await request.json()) as Partial<ResearchRequest>;
    const company = body.company?.trim();
    const product = body.product?.trim();
    if (!company || !product) return NextResponse.json({ error: "Target enterprise and product description are required." }, { status: 400 });
    if (company.length > 180 || product.length > 2_500 || (body.geography?.length ?? 0) > 180) {
      return NextResponse.json({ error: "One or more inputs exceed the supported length." }, { status: 400 });
    }
    return NextResponse.json(await runResearch({ company, product, geography: body.geography?.trim() || undefined }));
  } catch (error) {
    return NextResponse.json({ error: error instanceof Error ? error.message : "Research failed unexpectedly." }, { status: 500 });
  }
}
