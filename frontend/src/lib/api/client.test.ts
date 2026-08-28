import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  requestHeaders: vi.fn(),
}));

vi.mock("next/headers", () => ({ headers: mocks.requestHeaders }));

import { createApiClient } from "./client";

describe("server API client correlation", () => {
  beforeEach(() => {
    mocks.requestHeaders.mockReset();
  });

  it("forwards the edge request identifier to the private API", async () => {
    mocks.requestHeaders.mockResolvedValue(new Headers({ "x-request-id": "edge-request-123" }));
    const fetchMock = vi.fn(async (request: Request) => {
      expect(request.headers.get("x-request-id")).toBe("edge-request-123");
      return new Response(JSON.stringify({ status: "ok" }), {
        status: 200,
        headers: { "content-type": "application/json" },
      });
    });
    vi.stubGlobal("fetch", fetchMock);

    await createApiClient().GET("/health");

    expect(fetchMock).toHaveBeenCalledOnce();
    vi.unstubAllGlobals();
  });
});
