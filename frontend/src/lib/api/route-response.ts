import "server-only";

import { createApiClient, type ApiClient } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import { getSessionToken } from "@/lib/auth/session";

export async function bffResponse<T>(
  call: (api: ApiClient) => Promise<{ data?: T }>,
): Promise<Response> {
  try {
    const { data } = await call(createApiClient(await getSessionToken()));
    if (data === undefined) throw new Error("Backend returned an empty response");
    return Response.json(data, { headers: { "cache-control": "no-store" } });
  } catch (error) {
    if (error instanceof ApiError) {
      return Response.json(
        {
          error: {
            code: error.code,
            message: error.message,
            details: error.details ?? {},
            request_id: error.requestId,
          },
        },
        { status: error.status, headers: { "cache-control": "no-store" } },
      );
    }
    return Response.json(
      {
        error: {
          code: "INTERNAL_SERVER_ERROR",
          message: "The request could not be completed",
          details: {},
        },
      },
      { status: 500, headers: { "cache-control": "no-store" } },
    );
  }
}
