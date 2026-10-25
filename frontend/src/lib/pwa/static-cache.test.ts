// @vitest-environment node
import { readFileSync } from "node:fs";
import { runInNewContext } from "node:vm";
import { describe, expect, it, vi } from "vitest";

const source = readFileSync("public/driver-sw.js", "utf8");
const origin = "https://cardvert.test";

function worker(release: string, stores = new Map<string, Map<string, Response>>()) {
  const handlers: Record<string, (event: unknown) => void> = {};
  const fetch = vi.fn(async () => new Response("chunk"));
  const caches = {
    keys: async () => [...stores.keys()],
    delete: async (name: string) => stores.delete(name),
    open: async (name: string) => {
      const entries = stores.get(name) ?? new Map<string, Response>();
      stores.set(name, entries);
      return {
        match: async (req: Request) => entries.get(req.url)?.clone(),
        put: async (req: Request, res: Response) => {
          entries.set(req.url, res);
        },
        keys: async () => [...entries.keys()].map((url) => new Request(url)),
        delete: async (req: Request) => entries.delete(req.url),
      };
    },
  };
  runInNewContext(source, {
    URL,
    Response,
    fetch,
    caches,
    self: {
      location: new URL(`${origin}/driver-sw.js?release=${release}`),
      addEventListener: (name: string, handler: (event: unknown) => void) => {
        handlers[name] = handler;
      },
      skipWaiting: vi.fn(),
      clients: { claim: vi.fn() },
    },
  });
  return {
    stores,
    fetch,
    async activate() {
      let pending: Promise<unknown> | undefined;
      const activate = handlers.activate;
      if (!activate) throw new Error("Service worker did not register its activate handler");
      activate({
        waitUntil: (promise: Promise<unknown>) => {
          pending = promise;
        },
      });
      if (!pending) throw new Error("Service worker did not provide activation work");
      await pending;
    },
    async request(path: string, mode = "cors", method = "GET") {
      let response: Promise<Response> | undefined;
      const onFetch = handlers.fetch;
      if (!onFetch) throw new Error("Service worker did not register its fetch handler");
      onFetch({
        request: { url: new URL(path, origin).href, mode, method },
        respondWith: (promise: Promise<Response>) => {
          response = promise;
        },
      });
      return response;
    },
  };
}

describe("bounded driver static cache", () => {
  it("bounds concurrent same-release writes and serves cache hits", async () => {
    const sw = worker("first");
    await Promise.all(Array.from({ length: 90 }, (_, i) => sw.request(`/_next/static/${i}.js`)));
    const entries = [...sw.stores.values()][0];
    if (!entries) throw new Error("Static requests did not create a cache");
    expect(entries.size).toBe(64);
    const retained = [...entries.keys()][63];
    if (!retained) throw new Error("Static cache did not retain its 64th entry");
    sw.fetch.mockClear();
    const cached = await sw.request(retained);
    if (!cached) throw new Error("Service worker did not respond to the retained static request");
    expect(await cached.text()).toBe("chunk");
    expect(sw.fetch).not.toHaveBeenCalled();
  });

  it("removes prior release caches while preserving unrelated origin data", async () => {
    const first = worker("first");
    await first.request("/_next/static/old.js");
    first.stores.set(
      "another-app",
      new Map([[`${origin}/unrelated`, new Response("preserve unrelated data")]]),
    );
    const next = worker("next", first.stores);
    await next.request("/_next/static/new.js");
    await next.activate();
    expect([...next.stores.keys()].sort()).toEqual([
      "another-app",
      "cardvert-driver-static-v4-next",
    ]);
    expect(await next.stores.get("another-app")?.get(`${origin}/unrelated`)?.text()).toBe(
      "preserve unrelated data",
    );
  });

  it("keeps APIs, auth, other origins and non-GET requests outside the cache", async () => {
    const sw = worker("current");
    for (const path of [
      "/api/driver/trips",
      "/login",
      "/driver/keepalive",
      "https://other.test/_next/static/a.js",
    ])
      expect(await sw.request(path)).toBeUndefined();
    expect(await sw.request("/_next/static/a.js", "cors", "POST")).toBeUndefined();
    expect(sw.stores.size).toBe(0);
    sw.fetch.mockRejectedValueOnce(new Error("offline"));
    const offline = await sw.request("/driver", "navigate");
    expect(offline?.status).toBe(503);
    expect(offline?.headers.get("cache-control")).toBe("no-store");
    const html = await offline?.text();
    expect(html).toContain("This offline page is not tracking your location");
    expect(html).toContain("Fresh earnings and review details are unavailable");
    expect(sw.stores.size).toBe(0);
  });
});
