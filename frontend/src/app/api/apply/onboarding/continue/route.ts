import { z } from "zod";
import { createApiClient } from "@/lib/api/client";
import { continueDriverApplication } from "@/lib/api/audit-batch2";
import { validContinuation } from "@/lib/apply/continuation";

export const dynamic = "force-dynamic";
const bodySchema = z.object({ application_access_token: z.string().min(1).max(8192) }).strict();
export async function POST(request: Request) {
  const unavailable = () =>
    Response.json(
      { error: { message: "This application link isn’t available. Ask for a new link." } },
      { status: 404, headers: { "cache-control": "no-store" } },
    );
  try {
    const parsed = bodySchema.safeParse(await request.json());
    if (!parsed.success) return unavailable();
    const { data } = await continueDriverApplication(
      createApiClient(),
      parsed.data.application_access_token,
    );
    const next = validContinuation(data);
    if (!next) return unavailable();
    return Response.json(next, { headers: { "cache-control": "no-store" } });
  } catch {
    return unavailable();
  }
}
