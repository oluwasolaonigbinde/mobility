import { headers } from "next/headers";
import { createRelayedApiClient } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import { loginClientIpHeader } from "@/lib/auth/client-ip";
import { getSessionToken } from "@/lib/auth/session";
import { env } from "@/lib/env";
import type { operations } from "@/lib/api/schema";

export const dynamic = "force-dynamic";

type FeedbackCreate =
  operations["submit_feedback_api_v1_feedback_post"]["requestBody"]["content"]["application/json"];

const MAX_BODY_BYTES = 1024 * 1024;
const NO_STORE = { "cache-control": "no-store" };

function deny(status: number, code: string, message: string, extra: Record<string, string> = {}) {
  return Response.json(
    { error: { code, message, details: {} } },
    { status, headers: { ...NO_STORE, ...extra } },
  );
}

const tooLarge = () => deny(413, "request_too_large", "Feedback is too large.");

/** Read at most 1 MiB; anything longer is refused without buffering the rest. */
async function readCapped(request: Request): Promise<string | null> {
  if (Number(request.headers.get("content-length")) > MAX_BODY_BYTES) return null;
  const reader = request.body?.getReader();
  if (!reader) return "";
  const chunks: Uint8Array[] = [];
  let size = 0;
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    size += value.byteLength;
    if (size > MAX_BODY_BYTES) {
      await reader.cancel();
      return null;
    }
    chunks.push(value);
  }
  const bytes = new Uint8Array(size);
  let offset = 0;
  for (const chunk of chunks) {
    bytes.set(chunk, offset);
    offset += chunk.byteLength;
  }
  return new TextDecoder().decode(bytes);
}

/** Same-origin submit for the site-wide feedback button (REQ-336). */
export async function POST(request: Request) {
  const text = await readCapped(request);
  if (text === null) return tooLarge();
  let body: FeedbackCreate;
  try {
    body = JSON.parse(text) as FeedbackCreate;
  } catch {
    return deny(422, "validation_error", "Check your feedback details.");
  }
  let retryAfter: string | null = null;
  try {
    const ip = loginClientIpHeader(await headers(), env().LOGIN_RATE_LIMIT_RELAY_CLIENT_IP_HEADER);
    const api = createRelayedApiClient(await getSessionToken(), ip);
    // Runs before the client's error middleware, which keeps only the body.
    api.use({
      onResponse({ response }) {
        retryAfter = response.headers.get("retry-after");
        return response;
      },
    });
    await api.POST("/api/v1/feedback", { body });
    return Response.json({ status: "received" }, { headers: NO_STORE });
  } catch (error) {
    if (error instanceof ApiError) {
      if (error.status === 429) {
        return deny(429, error.code, error.message, { "retry-after": retryAfter ?? "60" });
      }
      if ([404, 413, 415, 422, 503].includes(error.status))
        return deny(error.status, error.code, error.message);
    }
    return deny(502, "FEEDBACK_UNAVAILABLE", "Feedback is unavailable. Try again later.");
  }
}
