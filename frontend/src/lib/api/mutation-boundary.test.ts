// @vitest-environment node
import { afterEach, describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";
import { mutationBoundary } from "./mutation-boundary";

afterEach(() => vi.unstubAllEnvs());

describe("empty commands across proxy framing", () => {
  const paths = [
    "/api/notifications/read-all",
    "/api/notifications/notice/read",
    "/api/advertiser/files/uploads/file/confirm",
    "/api/driver/files/uploads/file/confirm",
    "/api/admin/files/file/installation-review",
  ];
  function request(path: string, headers: Record<string, string> = {}, body?: BodyInit) {
    vi.stubEnv("PUBLIC_ORIGIN", "http://localhost:3000");
    return new NextRequest(`http://localhost:3000${path}`, {
      method: "POST",
      headers: { origin: "http://localhost:3000", ...headers },
      body,
      ...(body instanceof ReadableStream ? { duplex: "half" } : {}),
    });
  }
  it.each(paths)("accepts direct empty POST %s", async (path) => {
    expect(await mutationBoundary(request(path))).toBeUndefined();
  });
  it.each(paths)("accepts empty JSON proxy framing %s", async (path) => {
    expect(
      await mutationBoundary(
        request(path, {
          "content-type": "application/json",
          "content-length": "0",
        }),
      ),
    ).toBeUndefined();
  });
  it.each(paths)("accepts zero-byte chunked proxy framing %s", async (path) => {
    const empty = new ReadableStream({
      start(controller) {
        controller.close();
      },
    });
    expect(
      await mutationBoundary(request(path, { "transfer-encoding": "chunked" }, empty)),
    ).toBeUndefined();
  });
  it.each(paths)("rejects actual body bytes %s", async (path) => {
    expect((await mutationBoundary(request(path, {}, "{}")))?.status).toBe(415);
  });
  it("fails closed on an unreadable stream", async () => {
    const broken = new ReadableStream({
      start(controller) {
        controller.error(new Error("broken"));
      },
    });
    expect((await mutationBoundary(request(paths[0]!, {}, broken)))?.status).toBe(400);
  });
  it("fails closed when the body stream is already locked", async () => {
    const req = request(
      paths[0]!,
      {},
      new ReadableStream({
        start(c) {
          c.close();
        },
      }),
    );
    const reader = req.body!.getReader();
    expect((await mutationBoundary(req))?.status).toBe(400);
    reader.releaseLock();
  });
  it("retains origin and ordinary JSON requirements", async () => {
    expect(
      (await mutationBoundary(request(paths[0]!, { origin: "https://hostile.example" })))?.status,
    ).toBe(403);
    expect(
      (await mutationBoundary(request(paths[0]!, { "sec-fetch-site": "cross-site" })))?.status,
    ).toBe(403);
    expect((await mutationBoundary(request("/api/other")))?.status).toBe(415);
  });
});
