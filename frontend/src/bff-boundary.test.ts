import { NextRequest } from "next/server";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { unstable_doesMiddlewareMatch } from "next/experimental/testing/server";
import proxy, { config } from "./proxy";

beforeEach(() => {
  vi.stubEnv("PUBLIC_ORIGIN", "https://app.example.com");
  vi.stubGlobal("fetch", vi.fn());
});
afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

function request(
  path = "/api/driver/files/uploads",
  headers: Record<string, string> = {},
  body: string | undefined = "{}",
) {
  return new NextRequest(`https://app.example.com${path}`, {
    method: "POST",
    body,
    headers: {
      cookie: "mobility_session=token",
      origin: "https://app.example.com",
      "content-type": "application/json",
      ...headers,
    },
  });
}

it.each<Record<string, string>>([
  { origin: "https://hostile.example.com", "sec-fetch-site": "same-site" },
  { origin: "null" },
  { origin: "" },
  { origin: "https://app.example.com.evil.test" },
  { origin: "https://app.example.com:8443" },
  { "sec-fetch-site": "cross-site" },
  { "sec-fetch-site": "same-site" },
  { "sec-fetch-mode": "no-cors" },
  { "sec-fetch-dest": "iframe" },
])(
  "denies hostile or contradictory browser metadata before downstream calls: %j",
  async (headers) => {
    const result = await proxy(request(undefined, headers));
    expect(result.status).toBe(403);
    expect(fetch).not.toHaveBeenCalled();
  },
);

it.each(["text/plain", "application/x-www-form-urlencoded", "multipart/form-data; boundary=x", ""])(
  "rejects %s on JSON mutations",
  async (type) => {
    expect((await proxy(request(undefined, { "content-type": type }))).status).toBe(415);
  },
);

it("allows exact Origin without Fetch Metadata and leaves the body intact", async () => {
  const req = request();
  expect((await proxy(req)).status).toBe(200);
  expect(await req.json()).toEqual({});
});

it("fails closed on missing production origin and ignores forwarded-host claims", async () => {
  vi.stubEnv("NODE_ENV", "production");
  vi.stubEnv("PUBLIC_ORIGIN", "");
  expect((await proxy(request(undefined, { "x-forwarded-host": "app.example.com" }))).status).toBe(
    503,
  );
});

it("permits bodyless notification commands but refuses an attached form body", async () => {
  const empty = new NextRequest("https://app.example.com/api/notifications/read-all", {
    method: "POST",
    headers: { origin: "https://app.example.com" },
  });
  expect((await proxy(empty)).status).toBe(200);
  expect(
    (
      await proxy(
        request("/api/notifications/read-all", { "content-type": "text/plain" }, "attack"),
      )
    ).status,
  ).toBe(415);
});

it.each([false, true])(
  "checks actual bytes in Next's bodyless POST stream (has bytes: %s)",
  async (hasBytes) => {
    const body = new ReadableStream<Uint8Array>({
      start(controller) {
        if (hasBytes) controller.enqueue(new TextEncoder().encode("unexpected"));
        controller.close();
      },
    });
    const req = new NextRequest("https://app.example.com/api/notifications/read-all", {
      method: "POST",
      body,
      headers: { origin: "https://app.example.com" },
      ...{ duplex: "half" },
    });
    expect((await proxy(req)).status).toBe(hasBytes ? 415 : 200);
  },
);

it("preserves the explicitly supported export form with exact origin", async () => {
  const req = request(
    "/api/advertiser/exposure-segments/segment/export",
    {
      "content-type": "application/x-www-form-urlencoded",
      "sec-fetch-mode": "navigate",
      "sec-fetch-dest": "document",
      "sec-fetch-site": "same-origin",
    },
    "approval_id=approved",
  );
  expect((await proxy(req)).status).toBe(200);
});

function routes(path: string): string[] {
  return readdirSync(path, { withFileTypes: true }).flatMap((entry) =>
    entry.isDirectory()
      ? routes(join(path, entry.name))
      : entry.name === "route.ts"
        ? [join(path, entry.name)]
        : [],
  );
}
it("covers every custom BFF unsafe entry point with the shared boundary", async () => {
  const inventory = routes("src/app/api");
  let tested = 0;
  for (const file of inventory) {
    const methods = [
      ...readFileSync(file, "utf8").matchAll(/export async function (POST|PUT|PATCH|DELETE)\(/g),
    ];
    for (const [, method] of methods) {
      const url = file
        .replace("src/app", "")
        .replace("/route.ts", "")
        .replace(/\[[^\]]+\]/g, "test-id");
      expect(unstable_doesMiddlewareMatch({ config, nextConfig: {}, url })).toBe(true);
      const req = new NextRequest(`https://app.example.com${url}`, {
        method,
        headers: { origin: "https://hostile.example.com", cookie: "mobility_session=token" },
      });
      expect((await proxy(req)).status).toBe(403);
      tested++;
    }
  }
  expect(tested).toBeGreaterThan(15);
  expect(fetch).not.toHaveBeenCalled();
});
