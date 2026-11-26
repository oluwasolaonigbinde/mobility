import { publicActionError } from "@/lib/api/public-action-error";
import { ApiError } from "@/lib/api/errors";
import { unstable_rethrow } from "next/navigation";

/**
 * `messages` maps the refusal codes a route actually returns to fixed public copy.
 * Only `error.message` is replaced; status, code, details and request id pass through.
 */
export function reportIssuanceError(
  error: unknown,
  messages: Readonly<Record<string, string>> = {},
): Response {
  unstable_rethrow(error);
  if (error instanceof ApiError) {
    return Response.json(
      {
        error: {
          code: error.code,
          message: publicActionError(error, messages),
          details: {},
          request_id: error.requestId,
        },
      },
      { status: error.status, headers: { "cache-control": "no-store" } },
    );
  }
  return Response.json(
    {
      error: {
        code: "REPORT_ISSUANCE_UNAVAILABLE",
        message: "The report issuance request could not be completed",
        details: {},
      },
    },
    { status: 500, headers: { "cache-control": "no-store" } },
  );
}
