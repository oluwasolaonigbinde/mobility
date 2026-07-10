import "server-only";
import createClient, { type Middleware } from "openapi-fetch";
import type { paths } from "./schema";
import { env } from "@/lib/env";
import { toApiError } from "./errors";

/**
 * Server-side API client (BFF pattern).
 *
 * The browser never calls FastAPI directly. Server Components, Server
 * Actions, and Route Handlers create a client with the caller's JWT
 * (read from the httpOnly session cookie) and talk to the backend over
 * the internal network.
 *
 * Every non-OK response is thrown as a typed ApiError, so call sites
 * handle one error shape everywhere.
 */

const throwOnError: Middleware = {
  async onResponse({ response }) {
    if (!response.ok) {
      const body: unknown = await response
        .clone()
        .json()
        .catch(() => undefined);
      throw toApiError(response.status, body);
    }
    return response;
  },
};

export type ApiClient = ReturnType<typeof createClient<paths>>;

export function createApiClient(token?: string): ApiClient {
  const client = createClient<paths>({
    baseUrl: env().API_BASE_URL,
    headers: token ? { Authorization: `Bearer ${token}` } : undefined,
    // Backend data changes independently of the Next build — never cache by default.
    cache: "no-store",
  });
  client.use(throwOnError);
  return client;
}
