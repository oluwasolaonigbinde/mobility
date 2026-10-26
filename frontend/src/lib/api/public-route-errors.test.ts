// @vitest-environment node
import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "./errors";
import { notFound, redirect } from "next/navigation";

vi.mock("./client", () => ({ createApiClient: () => ({}) }));
vi.mock("@/lib/auth/session", () => ({ getSessionToken: async () => "synthetic" }));
import { bffResponse } from "./route-response";
import { notificationResponse } from "@/app/api/notifications/_proxy";
import { fileResponse } from "@/app/api/advertiser/files/_proxy";
import { reportIssuanceError } from "@/app/api/advertiser/report-issuances/_responses";

afterEach(() => vi.restoreAllMocks());

const helpers = [
  [
    "shared BFF",
    (error: unknown) =>
      bffResponse(async () => {
        throw error;
      }),
  ],
  [
    "notifications",
    (error: unknown) =>
      notificationResponse(async () => {
        throw error;
      }),
  ],
  [
    "files",
    (error: unknown) =>
      fileResponse(async () => {
        throw error;
      }),
  ],
  ["report issuances", (error: unknown) => reportIssuanceError(error)],
] as const;

describe.each(helpers)("%s response errors", (_label, respond) => {
  it.each([
    ["redirect", () => redirect("/login")],
    ["notFound", () => notFound()],
  ] as const)(
    "rethrows the real Next %s signal before classifying errors",
    async (_name, navigate) => {
      const log = vi.spyOn(console, "warn").mockImplementation(() => undefined);
      let signal: unknown;
      try {
        navigate();
      } catch (error) {
        signal = error;
      }
      if (!(signal instanceof Error)) throw new Error("Next did not throw a navigation signal");
      await expect(Promise.resolve().then(() => respond(signal))).rejects.toBe(signal);
      expect(log).not.toHaveBeenCalled();
    },
  );

  it.each([401, 403, 404, 422, 500])(
    "preserves %s and machine codes without backend text or private details",
    async (status) => {
      vi.spyOn(console, "warn").mockImplementation(() => undefined);
      const response = await respond(
        new ApiError(status, {
          code: "TEST_ERROR",
          message: "private bank NIN token",
          details: { token: "private", lat: 9.0765 },
          request_id: "synthetic-request",
        }),
      );
      expect(response.status).toBe(status);
      expect(response.headers.get("cache-control")).toBe("no-store");
      const body = await response.json();
      expect(body.error).toMatchObject({
        code: "TEST_ERROR",
        details: {},
        request_id: "synthetic-request",
      });
      expect(JSON.stringify(body)).not.toMatch(/private|bank|NIN|token|9\.0765/);
    },
  );

  it("returns an honest failure on transport rejection", async () => {
    const response = await respond(new TypeError("private transport URL"));
    expect(response.status).toBe(500);
    expect(await response.text()).not.toContain("private");
  });
});
