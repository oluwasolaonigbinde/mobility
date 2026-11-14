import { beforeEach, describe, expect, it, vi } from "vitest";
import { isUuidParam, storageUrl, unknownIdResponse } from "./route-params";

const mocks = vi.hoisted(() => ({ client: vi.fn(), get: vi.fn(), post: vi.fn() }));
vi.mock("@/lib/api/client", () => ({ createApiClient: mocks.client }));
vi.mock("@/lib/auth/session", () => ({ getSessionToken: async () => "session" }));

const id = "00000000-0000-4000-8000-000000000001";
type Handler = (request: Request, context: { params: Promise<never> }) => Promise<Response>;
type RouteCase = {
  name: string;
  load: () => Promise<Record<string, unknown>>;
  method: "GET" | "POST";
  params: (value: string) => Record<string, string>;
  query?: string;
};

// The 14 dynamic BFF handlers that relayed path ids unchecked before REQ-316 (audit finding 9).
const routes: RouteCase[] = [
  {
    name: "admin campaign report re-run",
    load: () => import("@/app/api/admin/campaigns/[campaignId]/reports/re-run/route"),
    method: "POST",
    params: (value) => ({ campaignId: value }),
  },
  {
    name: "admin installation review",
    load: () => import("@/app/api/admin/files/[fileId]/installation-review/route"),
    method: "POST",
    params: (value) => ({ fileId: value }),
  },
  {
    name: "admin report download",
    load: () => import("@/app/api/admin/reports/[reportId]/download/route"),
    method: "GET",
    params: (value) => ({ reportId: value }),
    query: "?format=csv",
  },
  {
    name: "advertiser upload confirm",
    load: () => import("@/app/api/advertiser/files/uploads/[uploadId]/confirm/route"),
    method: "POST",
    params: (value) => ({ uploadId: value }),
  },
  {
    name: "advertiser file read",
    load: () => import("@/app/api/advertiser/files/[fileId]/route"),
    method: "GET",
    params: (value) => ({ fileId: value }),
  },
  {
    name: "advertiser report-issuance artifact download",
    load: () =>
      import("@/app/api/advertiser/report-issuances/[issuanceId]/artifacts/[format]/download/route"),
    method: "GET",
    params: (value) => ({ issuanceId: value, format: "csv" }),
  },
  {
    name: "advertiser report download",
    load: () => import("@/app/api/advertiser/reports/[reportId]/download/route"),
    method: "GET",
    params: (value) => ({ reportId: value }),
    query: "?format=pdf",
  },
  {
    name: "applicant file status",
    load: () => import("@/app/api/apply/onboarding/files/[fileId]/status/route"),
    method: "POST",
    params: (value) => ({ fileId: value }),
  },
  {
    name: "applicant upload confirm",
    load: () => import("@/app/api/apply/onboarding/uploads/[uploadId]/confirm/route"),
    method: "POST",
    params: (value) => ({ uploadId: value }),
  },
  {
    name: "driver installation evidence",
    load: () => import("@/app/api/driver/assignments/[assignmentId]/installation-evidence/route"),
    method: "POST",
    params: (value) => ({ assignmentId: value }),
  },
  {
    name: "driver upload confirm",
    load: () => import("@/app/api/driver/files/uploads/[uploadId]/confirm/route"),
    method: "POST",
    params: (value) => ({ uploadId: value }),
  },
  {
    name: "driver file read",
    load: () => import("@/app/api/driver/files/[fileId]/route"),
    method: "GET",
    params: (value) => ({ fileId: value }),
  },
  {
    name: "driver vehicle documents",
    load: () => import("@/app/api/driver/vehicles/[vehicleId]/documents/route"),
    method: "POST",
    params: (value) => ({ vehicleId: value }),
  },
  {
    name: "notification read",
    load: () => import("@/app/api/notifications/[notificationId]/read/route"),
    method: "POST",
    params: (value) => ({ notificationId: value }),
  },
];

async function call(route: RouteCase, value: string) {
  const handler = (await route.load())[route.method] as Handler;
  const request = new Request(`http://localhost/api/test${route.query ?? ""}`, {
    method: route.method,
    ...(route.method === "POST"
      ? { body: "{}", headers: { "content-type": "application/json" } }
      : {}),
  });
  return handler(request, { params: Promise.resolve(route.params(value)) as Promise<never> });
}

beforeEach(() => {
  vi.clearAllMocks();
  const result = { data: { url: "https://storage.example/signed", checksum_sha256: "abc" } };
  mocks.get.mockResolvedValue(result);
  mocks.post.mockResolvedValue(result);
  mocks.client.mockReturnValue({ GET: mocks.get, POST: mocks.post });
});

describe("dynamic BFF path ids", () => {
  it.each(routes.flatMap((route) => ["../me", "a/b", "not-a-uuid", ""].map((v) => [route, v])))(
    "%s refuses %j with 404 before calling the backend",
    async (route, value) => {
      const response = await call(route as RouteCase, value as string);
      expect(response.status).toBe(404);
      expect(response.headers.get("cache-control")).toBe("no-store");
      expect(mocks.client).not.toHaveBeenCalled();
    },
  );

  it.each(routes.map((route) => [route.name, route] as const))(
    "%s still relays a UUID to the backend",
    async (_name, route) => {
      await call(route, id);
      expect(mocks.client).toHaveBeenCalledTimes(1);
      expect(mocks.get.mock.calls.length + mocks.post.mock.calls.length).toBe(1);
    },
  );
});

describe("isUuidParam", () => {
  it("accepts only canonical UUIDs, every one of several", () => {
    expect(isUuidParam(id)).toBe(true);
    expect(isUuidParam(id, id.toUpperCase())).toBe(true);
    expect(isUuidParam(id, "x")).toBe(false);
    expect(isUuidParam(`${id}/x`)).toBe(false);
    expect(isUuidParam(id.replaceAll("-", ""))).toBe(false);
  });

  it("keeps only credential-free http(s) storage URLs", () => {
    expect(storageUrl("https://storage.example/a?sig=1")).toBe("https://storage.example/a?sig=1");
    expect(storageUrl("http://minio:9000/b")).toBe("http://minio:9000/b");
    for (const unsafe of [
      "javascript:alert(1)",
      "file:///etc/passwd",
      "https://user@storage.example/a",
      "https://:pw@storage.example/a",
      "/relative",
    ])
      expect(storageUrl(unsafe)).toBeNull();
  });

  it("builds a fixed, uncached 404 envelope with no request text", async () => {
    const response = unknownIdResponse();
    expect(response.status).toBe(404);
    expect(response.headers.get("cache-control")).toBe("no-store");
    expect(await response.json()).toEqual({
      error: { code: "NOT_FOUND", message: "That item was not found.", details: {} },
    });
  });
});
