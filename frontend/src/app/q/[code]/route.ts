import { env } from "@/lib/env";

export const dynamic = "force-dynamic";
const headers = {
  "cache-control": "no-store",
  "referrer-policy": "no-referrer",
  "x-content-type-options": "nosniff",
};

async function scan(method: "GET" | "HEAD", code: string) {
  if (!/^[a-f0-9]{32}$/.test(code))
    return new Response("This advert link is unavailable.", { status: 404, headers });
  try {
    // No cookies, IP, user agent, query or referrer are relayed to the scan counter.
    const response = await fetch(`${env().API_BASE_URL}/api/v1/qr/${code}`, {
      method,
      redirect: "manual",
      cache: "no-store",
      signal: AbortSignal.timeout(10000),
    });
    const location = response.headers.get("location");
    if (response.status === 302 && location && new URL(location).protocol === "https:")
      return new Response(null, { status: 302, headers: { ...headers, location } });
    return new Response(
      method === "HEAD" ? null : "This advert link is temporarily unavailable. Please try again.",
      {
        status: [404, 429].includes(response.status) ? response.status : 503,
        headers: {
          ...headers,
          ...(response.headers.has("retry-after")
            ? { "retry-after": response.headers.get("retry-after")! }
            : {}),
        },
      },
    );
  } catch {
    return new Response(
      method === "HEAD" ? null : "This advert link is temporarily unavailable. Please try again.",
      { status: 503, headers },
    );
  }
}
export async function GET(_request: Request, { params }: { params: Promise<{ code: string }> }) {
  return scan("GET", (await params).code);
}
export async function HEAD(_request: Request, { params }: { params: Promise<{ code: string }> }) {
  return scan("HEAD", (await params).code);
}
