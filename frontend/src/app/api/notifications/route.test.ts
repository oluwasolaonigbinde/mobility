import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@/lib/api/errors";
import { GET as notificationList } from "./route";
import { GET as unreadCount } from "./unread-count/route";
import { POST as markAllRead } from "./read-all/route";
import { POST as markRead } from "./[notificationId]/read/route";
import {
  GET as preferenceGet,
  PATCH as preferencePatch,
} from "../advertiser/notification-preferences/route";

const mocks = vi.hoisted(() => ({
  getSessionToken: vi.fn(),
  createApiClient: vi.fn(),
  get: vi.fn(),
  post: vi.fn(),
  patch: vi.fn(),
}));

vi.mock("@/lib/auth/session", () => ({ getSessionToken: mocks.getSessionToken }));
vi.mock("@/lib/api/client", () => ({
  createApiClient: mocks.createApiClient,
}));

describe("notification BFF routes", () => {
  beforeEach(() => {
    mocks.getSessionToken.mockReset().mockResolvedValue("http-only-token");
    mocks.get.mockReset();
    mocks.post.mockReset();
    mocks.patch.mockReset();
    mocks.createApiClient.mockReset().mockReturnValue({
      GET: mocks.get,
      POST: mocks.post,
      PATCH: mocks.patch,
    });
  });

  it("uses the server session client for list, count and read mutations", async () => {
    mocks.get
      .mockResolvedValueOnce({ data: { items: [], total: 0, limit: 50, offset: 0 } })
      .mockResolvedValueOnce({ data: { unread_count: 2 } });
    mocks.post
      .mockResolvedValueOnce({ data: { unread_count: 0 } })
      .mockResolvedValueOnce({ data: { id: "notice-1", read_at: "2026-08-24T12:00:00Z" } });

    expect(
      await (await notificationList(new Request("http://localhost/api/notifications"))).json(),
    ).toMatchObject({ items: [] });
    expect(await (await unreadCount()).json()).toEqual({ unread_count: 2 });
    expect(await (await markAllRead()).json()).toEqual({ unread_count: 0 });
    expect(
      await (
        await markRead(new Request("http://localhost/api/notifications/notice-1/read"), {
          params: Promise.resolve({ notificationId: "notice-1" }),
        })
      ).json(),
    ).toMatchObject({ id: "notice-1" });

    expect(mocks.createApiClient).toHaveBeenCalledWith("http-only-token");
    expect(mocks.get).toHaveBeenNthCalledWith(1, "/api/v1/notifications");
    expect(mocks.get).toHaveBeenNthCalledWith(2, "/api/v1/notifications/unread-count");
    expect(mocks.post).toHaveBeenNthCalledWith(1, "/api/v1/notifications/read-all");
    expect(mocks.post).toHaveBeenNthCalledWith(2, "/api/v1/notifications/{notification_id}/read", {
      params: { path: { notification_id: "notice-1" } },
    });
  });

  it("forwards only valid paging integers and rejects malformed ones", async () => {
    mocks.get.mockResolvedValue({ data: { items: [], total: 70, limit: 20, offset: 40 } });

    const page = await notificationList(
      new Request("http://localhost/api/notifications?limit=20&offset=40&role=admin"),
    );
    expect(page.status).toBe(200);
    expect(mocks.get).toHaveBeenCalledWith("/api/v1/notifications", {
      params: { query: { limit: 20, offset: 40 } },
    });

    for (const bad of ["limit=0", "limit=101", "limit=2.5", "offset=-1", "offset=abc"]) {
      const response = await notificationList(
        new Request(`http://localhost/api/notifications?${bad}`),
      );
      expect(response.status).toBe(400);
      expect((await response.json()).error.code).toBe("INVALID_PAGE");
    }
    expect(mocks.get).toHaveBeenCalledTimes(1);
  });

  it("preserves backend error envelopes and proxies advertiser preferences", async () => {
    mocks.get
      .mockRejectedValueOnce(
        new ApiError(403, {
          code: "FORBIDDEN_ROLE",
          message: "Advertiser role is required",
          details: { role: "admin" },
          request_id: "request-1",
        }),
      )
      .mockResolvedValueOnce({ data: { in_app_enabled: true, transactional_email_enabled: true } });
    mocks.patch.mockResolvedValueOnce({
      data: { in_app_enabled: true, transactional_email_enabled: false },
    });

    const rejected = await preferenceGet();
    expect(rejected.status).toBe(403);
    expect(await rejected.json()).toEqual({
      error: {
        code: "FORBIDDEN_ROLE",
        message: "Advertiser role is required",
        details: { role: "admin" },
        request_id: "request-1",
      },
    });
    expect(await (await preferenceGet()).json()).toEqual({
      in_app_enabled: true,
      transactional_email_enabled: true,
    });
    expect(
      await (
        await preferencePatch(
          new Request("http://localhost/api/advertiser/notification-preferences", {
            method: "PATCH",
            body: JSON.stringify({ transactional_email_enabled: false }),
          }),
        )
      ).json(),
    ).toEqual({ in_app_enabled: true, transactional_email_enabled: false });
    expect(mocks.patch).toHaveBeenCalledWith("/api/v1/advertiser/notification-preferences", {
      body: { transactional_email_enabled: false },
    });
  });
});
