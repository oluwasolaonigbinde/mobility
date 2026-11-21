import { ApiError } from "@/lib/api/errors";
import { bffResponse } from "@/lib/api/route-response";

export const dynamic = "force-dynamic";
export async function POST(request: Request) {
  const body = await request.json();
  let limiterCode: "BANK_CHECK_LIMITED" | "BANK_CHECK_LIMIT_UNAVAILABLE" | undefined;
  let retryAfter: string | undefined;
  const response = await bffResponse(async (api) => {
    try {
      return await api.POST("/api/v1/auth/driver-onboarding/account-name", {
        body,
        middleware: [
          {
            // The client normalizes errors after this route-specific middleware runs.
            onResponse({ response }) {
              const value = response.headers.get("retry-after");
              if (
                response.status === 429 &&
                value &&
                /^[1-9]\d{0,3}$/.test(value) &&
                Number(value) <= 3600
              ) {
                retryAfter = value;
              } else if (response.status === 503 && value === "1") {
                retryAfter = value;
              }
            },
          },
        ],
      });
    } catch (error) {
      if (
        error instanceof ApiError &&
        ((error.status === 429 && error.code === "BANK_CHECK_LIMITED") ||
          (error.status === 503 && error.code === "BANK_CHECK_LIMIT_UNAVAILABLE"))
      ) {
        limiterCode = error.code;
      }
      throw error;
    }
  });
  if (!limiterCode) return response;
  return Response.json(
    { error: { code: limiterCode } },
    {
      status: response.status,
      headers: {
        "cache-control": "no-store",
        ...(retryAfter ? { "retry-after": retryAfter } : {}),
      },
    },
  );
}
