import { notificationResponse } from "./_proxy";

export const dynamic = "force-dynamic";

const PAGE_LIMIT_MAX = 100;

function pageParam(value: string | null, min: number, max: number): number | null | undefined {
  if (value === null) return undefined;
  if (!/^\d+$/.test(value)) return null;
  const parsed = Number(value);
  return parsed >= min && parsed <= max ? parsed : null;
}

/** Forwards only the two paging integers the backend list accepts. */
export async function GET(request: Request) {
  const search = new URL(request.url).searchParams;
  const limit = pageParam(search.get("limit"), 1, PAGE_LIMIT_MAX);
  const offset = pageParam(search.get("offset"), 0, Number.MAX_SAFE_INTEGER);
  if (limit === null || offset === null) {
    return Response.json(
      {
        error: {
          code: "INVALID_PAGE",
          message: "limit must be 1–100 and offset must be zero or more",
          details: {},
        },
      },
      { status: 400, headers: { "cache-control": "no-store" } },
    );
  }
  const query = {
    ...(limit !== undefined ? { limit } : {}),
    ...(offset !== undefined ? { offset } : {}),
  };
  return notificationResponse((api) =>
    Object.keys(query).length
      ? api.GET("/api/v1/notifications", { params: { query } })
      : api.GET("/api/v1/notifications"),
  );
}
