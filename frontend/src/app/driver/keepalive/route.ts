import { validateDriverSession } from "@/lib/auth/driver-session";
import { clearSessionCookie } from "@/lib/auth/session";

export const dynamic = "force-dynamic";

export async function GET() {
  const session = await validateDriverSession();
  const headers = { "cache-control": "no-store" };
  if (session.status === "valid") {
    return Response.json(session, { status: 200, headers });
  }
  if (session.status === "unavailable") {
    return Response.json(session, { status: 503, headers });
  }
  await clearSessionCookie();
  return Response.json(session, {
    status: session.status === "wrong-role" ? 403 : 401,
    headers,
  });
}
