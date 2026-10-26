import { beforeEach, expect, it, vi } from "vitest";
const fetchMock = vi.hoisted(() => vi.fn());
vi.mock("@/lib/env", () => ({ env: () => ({ API_BASE_URL: "http://internal-api:8000" }) }));
import { GET, HEAD } from "./route";
const code = "a".repeat(32);
const params = { params: Promise.resolve({ code }) };
beforeEach(() => {
  vi.clearAllMocks();
  vi.stubGlobal("fetch", fetchMock);
});
it("relays only the random code and redirects to the server's stored https destination", async () => {
  fetchMock.mockResolvedValue(
    new Response(null, { status: 302, headers: { location: "https://example.com/menu" } }),
  );
  const response = await GET(
    new Request(`https://cardvert.example/q/${code}?url=https://attacker.com`, {
      headers: {
        cookie: "private",
        "user-agent": "private browser",
        "x-forwarded-for": "192.0.2.1",
      },
    }),
    params,
  );
  expect(response.status).toBe(302);
  expect(response.headers.get("location")).toBe("https://example.com/menu");
  expect(response.headers.get("cache-control")).toBe("no-store");
  expect(response.headers.get("referrer-policy")).toBe("no-referrer");
  expect(fetchMock).toHaveBeenCalledWith(
    `http://internal-api:8000/api/v1/qr/${code}`,
    expect.objectContaining({ method: "GET", redirect: "manual", cache: "no-store" }),
  );
  expect(fetchMock.mock.calls[0]![1]).not.toHaveProperty("headers");
});
it("uses HEAD without following a redirect or issuing a GET", async () => {
  fetchMock.mockResolvedValue(
    new Response(null, { status: 302, headers: { location: "https://example.com/" } }),
  );
  const response = await HEAD(
    new Request(`https://cardvert.example/q/${code}`, { method: "HEAD" }),
    params,
  );
  expect(response.status).toBe(302);
  expect(fetchMock.mock.calls[0]![1].method).toBe("HEAD");
  expect(await response.text()).toBe("");
});
it.each(["javascript:alert(1)", "http://example.com", "not a URL"])(
  "refuses an invalid upstream destination %s",
  async (location) => {
    fetchMock.mockResolvedValue(new Response(null, { status: 302, headers: { location } }));
    const response = await GET(new Request(`https://cardvert.example/q/${code}`), params);
    expect(response.status).toBe(503);
    expect(response.headers.has("location")).toBe(false);
  },
);
it("passes a bounded unavailable/rate-limited state without private upstream detail", async () => {
  fetchMock.mockResolvedValue(
    new Response("private detail", { status: 429, headers: { "retry-after": "45" } }),
  );
  const response = await GET(new Request(`https://cardvert.example/q/${code}`), params);
  expect(response.status).toBe(429);
  expect(response.headers.get("retry-after")).toBe("45");
  expect(await response.text()).not.toContain("private detail");
});
it("does not query malformed codes and fails closed on transport failure", async () => {
  expect(
    (
      await GET(new Request("https://cardvert.example/q/bad"), {
        params: Promise.resolve({ code: "bad" }),
      })
    ).status,
  ).toBe(404);
  expect(fetchMock).not.toHaveBeenCalled();
  fetchMock.mockRejectedValue(new Error("private failure"));
  expect((await GET(new Request(`https://cardvert.example/q/${code}`), params)).status).toBe(503);
});
