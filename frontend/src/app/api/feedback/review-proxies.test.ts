import { beforeEach, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({ fetch: vi.fn() }));
vi.mock("next/headers", () => ({ headers: async () => new Headers() }));
vi.mock("@/lib/env", () => ({ env: () => ({ API_BASE_URL: "http://api.test" }) }));

import { GET as exportCsv } from "./export/route";
import { GET as screenshot } from "./[feedbackId]/screenshot/route";

const ID = "10000000-0000-4000-8000-000000000001";
const shot = (id = ID) =>
  screenshot(new Request(`https://app.test/api/feedback/${id}/screenshot`), {
    params: Promise.resolve({ feedbackId: id }),
  });
const apiError = (status: number) =>
  Response.json({ error: { code: "X", message: "x", details: {} } }, { status });
const sent = () => mocks.fetch.mock.calls[0]![0] as Request;

beforeEach(() => {
  mocks.fetch.mockReset();
  vi.stubGlobal("fetch", mocks.fetch);
});

it("serves the screenshot as a private JPEG with no password or token", async () => {
  mocks.fetch.mockResolvedValue(
    new Response(new Uint8Array([0xff, 0xd8, 0xff]), { headers: { "content-type": "image/jpeg" } }),
  );
  const response = await shot();
  expect(response.status).toBe(200);
  expect(response.headers.get("content-type")).toBe("image/jpeg");
  expect(response.headers.get("cache-control")).toBe("private, no-store");
  expect(response.headers.get("x-content-type-options")).toBe("nosniff");
  expect(new Uint8Array(await response.arrayBuffer())).toEqual(new Uint8Array([0xff, 0xd8, 0xff]));
  expect(sent().url).toBe(`http://api.test/api/v1/feedback/${ID}/screenshot`);
  expect(sent().headers.get("x-feedback-review-token")).toBeNull();
});

it("refuses a bad id without calling the API", async () => {
  expect((await shot("../export.csv")).status).toBe(404);
  expect(mocks.fetch).not.toHaveBeenCalled();
});

it.each([
  [404, 404],
  [500, 503],
])("maps an upstream screenshot %s to %s", async (upstream, expected) => {
  mocks.fetch.mockResolvedValue(apiError(upstream));
  const response = await shot();
  expect(response.status).toBe(expected);
  expect(response.headers.get("cache-control")).toBe("private, no-store");
});

it("downloads the CSV as an attachment with no password or token", async () => {
  mocks.fetch.mockResolvedValue(
    new Response("created_at,status\n", { headers: { "content-type": "text/csv" } }),
  );
  const response = await exportCsv();
  expect(response.status).toBe(200);
  expect(response.headers.get("content-type")).toBe("text/csv; charset=utf-8");
  expect(response.headers.get("content-disposition")).toBe(
    'attachment; filename="cardvert-feedback.csv"',
  );
  expect(response.headers.get("cache-control")).toBe("private, no-store");
  expect(await response.text()).toBe("created_at,status\n");
  expect(sent().url).toBe("http://api.test/api/v1/feedback/export.csv");
  expect(sent().headers.get("x-feedback-review-token")).toBeNull();
});

it.each([
  [404, 404],
  [500, 503],
])("maps an upstream export %s to %s", async (upstream, expected) => {
  mocks.fetch.mockResolvedValue(apiError(upstream));
  expect((await exportCsv()).status).toBe(expected);
});
