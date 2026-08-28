import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Providers } from "@/app/providers";
import { NotificationCenter } from "./notification-center";

const router = vi.hoisted(() => ({ replace: vi.fn(), refresh: vi.fn() }));

vi.mock("next/navigation", () => ({ useRouter: () => router }));

function response(body: unknown) {
  return Promise.resolve(new Response(JSON.stringify(body), { status: 200 }));
}

function setVisibility(value: "visible" | "hidden") {
  Object.defineProperty(document, "visibilityState", { configurable: true, value });
  document.dispatchEvent(new Event("visibilitychange"));
}

function renderCentre(canManageAdvertiserPreferences = false) {
  return render(
    <Providers>
      <NotificationCenter canManageAdvertiserPreferences={canManageAdvertiserPreferences} />
    </Providers>,
  );
}

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
  setVisibility("visible");
  Object.defineProperty(navigator, "onLine", { configurable: true, value: true });
  window.dispatchEvent(new Event("online"));
  router.replace.mockReset();
  router.refresh.mockReset();
});

describe("NotificationCenter", () => {
  it("polls only the unread count while visible and fetches the list only on open", async () => {
    vi.useFakeTimers();
    const fetchMock = vi.fn((input: string) => {
      if (input === "/api/notifications/unread-count") return response({ unread_count: 3 });
      return response({ items: [], total: 0, limit: 50, offset: 0 });
    });
    vi.stubGlobal("fetch", fetchMock);
    renderCentre();

    await act(async () => undefined);
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/notifications/unread-count",
      expect.objectContaining({ headers: { "content-type": "application/json" } }),
    );
    expect(fetchMock).not.toHaveBeenCalledWith("/api/notifications", expect.anything());

    await act(async () => vi.advanceTimersByTimeAsync(45_000));
    expect(
      fetchMock.mock.calls.filter(([path]) => path === "/api/notifications/unread-count"),
    ).toHaveLength(2);
    setVisibility("hidden");
    await act(async () => vi.advanceTimersByTimeAsync(90_000));
    expect(
      fetchMock.mock.calls.filter(([path]) => path === "/api/notifications/unread-count"),
    ).toHaveLength(2);

    fireEvent.click(screen.getByRole("button", { name: /notifications/i }));
    await act(async () => undefined);
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/notifications",
      expect.objectContaining({ headers: { "content-type": "application/json" } }),
    );
  });

  it("invalidates the list and count after read mutations", async () => {
    const fetchMock = vi.fn((input: string, init?: RequestInit) => {
      if (input === "/api/notifications/unread-count") return response({ unread_count: 1 });
      if (input === "/api/notifications") {
        return response({
          items: [
            {
              id: "notice-1",
              title: "Trip payment on hold",
              body: "A trip payment is on hold.",
              channel: "in_app",
              type_key: "fraud_hold_raised",
              created_at: "2026-08-24T12:00:00Z",
              read_at: null,
            },
          ],
          total: 1,
          limit: 50,
          offset: 0,
        });
      }
      if (input === "/api/notifications/notice-1/read" && init?.method === "POST") {
        return response({ id: "notice-1", read_at: "2026-08-24T12:00:01Z" });
      }
      return response({ unread_count: 0 });
    });
    vi.stubGlobal("fetch", fetchMock);
    renderCentre();

    fireEvent.click(screen.getByRole("button", { name: /notifications/i }));
    await screen.findByText("Trip payment on hold");
    fireEvent.click(screen.getByRole("button", { name: "Mark read" }));
    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/notifications/notice-1/read",
        expect.objectContaining({ method: "POST" }),
      ),
    );
    await waitFor(() =>
      expect(fetchMock.mock.calls.filter(([path]) => path === "/api/notifications")).toHaveLength(
        2,
      ),
    );
    expect(
      fetchMock.mock.calls.filter(([path]) => path === "/api/notifications/unread-count").length,
    ).toBeGreaterThan(1);

    fireEvent.click(screen.getByRole("button", { name: "Mark all read" }));
    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/notifications/read-all",
        expect.objectContaining({ method: "POST" }),
      ),
    );
    await waitFor(() =>
      expect(fetchMock.mock.calls.filter(([path]) => path === "/api/notifications")).toHaveLength(
        3,
      ),
    );
  });

  it("renders the new activity notices with their truthful driver copy", async () => {
    const fetchMock = vi.fn((input: string) => {
      if (input === "/api/notifications/unread-count") return response({ unread_count: 1 });
      if (input === "/api/notifications") {
        return response({
          items: [
            {
              id: "activity-notice-1",
              title: "Verified activity below floor",
              body: "Your verified activity was below the configured weekly floor. Operations will review the assignment.",
              channel: "in_app",
              type_key: "activity_floor_breached",
              created_at: "2026-08-24T12:00:00Z",
              read_at: null,
            },
          ],
          total: 1,
          limit: 50,
          offset: 0,
        });
      }
      return response({ unread_count: 0 });
    });
    vi.stubGlobal("fetch", fetchMock);

    renderCentre();
    fireEvent.click(screen.getByRole("button", { name: /notifications/i }));

    expect(await screen.findByText("Verified activity below floor")).toBeInTheDocument();
    expect(
      screen.getByText(
        "Your verified activity was below the configured weekly floor. Operations will review the assignment.",
      ),
    ).toBeInTheDocument();
  });

  it("shows the organization-wide mandatory in-app setting and email toggle only to advertisers", async () => {
    const fetchMock = vi.fn((input: string, init?: RequestInit) => {
      if (input === "/api/notifications/unread-count") return response({ unread_count: 0 });
      if (input === "/api/notifications")
        return response({ items: [], total: 0, limit: 50, offset: 0 });
      if (input === "/api/advertiser/notification-preferences" && init?.method === "PATCH") {
        return response({ in_app_enabled: true, transactional_email_enabled: false });
      }
      return response({ in_app_enabled: true, transactional_email_enabled: true });
    });
    vi.stubGlobal("fetch", fetchMock);
    const { unmount } = renderCentre();
    fireEvent.click(screen.getByRole("button", { name: /notifications/i }));
    await screen.findByText("You are all caught up.");
    expect(screen.queryByText("ORGANIZATION DELIVERY PREFERENCES")).not.toBeInTheDocument();
    unmount();

    renderCentre(true);
    fireEvent.click(screen.getByRole("button", { name: /notifications/i }));
    await screen.findByText("In-app notifications are always on.");
    const email = screen.getByLabelText("Transactional email");
    await waitFor(() => expect(email).toBeChecked());
    fireEvent.click(email);
    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/advertiser/notification-preferences",
        expect.objectContaining({ method: "PATCH" }),
      ),
    );
  });

  it("surfaces failed mutations with accessible retry actions", async () => {
    let readAttempts = 0;
    let preferenceAttempts = 0;
    const fetchMock = vi.fn((input: string, init?: RequestInit) => {
      if (input === "/api/notifications/unread-count") return response({ unread_count: 1 });
      if (input === "/api/notifications") {
        return response({
          items: [
            {
              id: "notice-retry",
              title: "Trip verified",
              body: "Your trip was verified.",
              channel: "in_app",
              type_key: "trip_verified",
              created_at: "2026-08-24T12:00:00Z",
              read_at: null,
            },
          ],
          total: 1,
          limit: 50,
          offset: 0,
        });
      }
      if (input === "/api/notifications/notice-retry/read") {
        readAttempts += 1;
        return readAttempts === 1
          ? Promise.resolve(
              new Response(JSON.stringify({ error: { message: "Read request failed" } }), {
                status: 503,
              }),
            )
          : response({ id: "notice-retry", read_at: "2026-08-24T12:00:01Z" });
      }
      if (input === "/api/advertiser/notification-preferences" && init?.method === "PATCH") {
        preferenceAttempts += 1;
        return preferenceAttempts === 1
          ? Promise.resolve(
              new Response(JSON.stringify({ error: { message: "Preference request failed" } }), {
                status: 503,
              }),
            )
          : response({ in_app_enabled: true, transactional_email_enabled: false });
      }
      return response({ in_app_enabled: true, transactional_email_enabled: true });
    });
    vi.stubGlobal("fetch", fetchMock);
    renderCentre(true);

    fireEvent.click(screen.getByRole("button", { name: /notifications/i }));
    await screen.findByText("Trip verified");
    fireEvent.click(screen.getByRole("button", { name: "Mark read" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Read request failed");
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    await waitFor(() => expect(readAttempts).toBe(2));

    const email = screen.getByLabelText("Transactional email");
    fireEvent.click(email);
    await waitFor(() => expect(preferenceAttempts).toBe(1));
    expect(await screen.findByRole("alert")).toHaveTextContent("Preference request failed");
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    await waitFor(() => expect(preferenceAttempts).toBe(2));
  });

  it("hides cached notification authority and blocks mutations while offline", async () => {
    const fetchMock = vi.fn((input: string) => {
      if (input === "/api/notifications/unread-count") return response({ unread_count: 1 });
      return response({
        items: [
          {
            id: "notice-online-only",
            title: "Trip payment on hold",
            body: "A trip payment is on hold.",
            channel: "in_app",
            type_key: "fraud_hold_raised",
            created_at: "2026-08-27T12:00:00Z",
            read_at: null,
          },
        ],
        total: 1,
        limit: 50,
        offset: 0,
      });
    });
    vi.stubGlobal("fetch", fetchMock);
    Object.defineProperty(navigator, "onLine", { configurable: true, value: true });
    renderCentre();

    fireEvent.click(screen.getByRole("button", { name: /notifications/i }));
    expect(await screen.findByText("Trip payment on hold")).toBeInTheDocument();

    Object.defineProperty(navigator, "onLine", { configurable: true, value: false });
    act(() => window.dispatchEvent(new Event("offline")));

    expect(screen.queryByText("Trip payment on hold")).not.toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent(/reconnect to load current notifications/i);
    expect(screen.getByRole("button", { name: "Mark all read" })).toBeDisabled();
  });

  it("clears role-scoped notification state and redirects on session revocation", async () => {
    Object.defineProperty(navigator, "onLine", { configurable: true, value: true });
    window.dispatchEvent(new Event("online"));
    setVisibility("visible");
    const fetchMock = vi.fn((input: string) => {
      if (input.startsWith("/api/notifications")) {
        return Promise.resolve(
          new Response(
            JSON.stringify({ error: { code: "SESSION_REVOKED", message: "Session revoked" } }),
            { status: 401 },
          ),
        );
      }
      return response({ items: [], total: 0, limit: 50, offset: 0 });
    });
    vi.stubGlobal("fetch", fetchMock);
    renderCentre();
    fireEvent.click(screen.getByRole("button", { name: "Notifications" }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    await waitFor(() => expect(router.replace).toHaveBeenCalledWith("/login"));
    expect(screen.getByRole("button", { name: "Notifications" })).not.toHaveTextContent(/\d/);
  });

  it("removes the previous user's cached notices when the session scope changes", async () => {
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false } },
    });
    let activeTitle = "Driver A private notice";
    const fetchMock = vi.fn((input: string) => {
      if (input === "/api/notifications/unread-count") return response({ unread_count: 1 });
      return response({
        items: [
          {
            id: activeTitle.startsWith("Driver A") ? "notice-a" : "notice-b",
            title: activeTitle,
            body: "A sanitized account update.",
            channel: "in_app",
            type_key: "fraud_review_resolved",
            created_at: "2026-08-28T03:00:00Z",
            read_at: null,
          },
        ],
        total: 1,
        limit: 50,
        offset: 0,
      });
    });
    vi.stubGlobal("fetch", fetchMock);

    const view = render(
      <QueryClientProvider client={client}>
        <NotificationCenter sessionScope="driver-a" />
      </QueryClientProvider>,
    );
    fireEvent.click(screen.getByRole("button", { name: /notifications/i }));
    expect(await screen.findByText("Driver A private notice")).toBeInTheDocument();
    expect(client.getQueryData(["notifications", "driver-a", "list"])).toBeDefined();

    activeTitle = "Driver B private notice";
    view.rerender(
      <QueryClientProvider client={client}>
        <NotificationCenter sessionScope="driver-b" />
      </QueryClientProvider>,
    );

    expect(await screen.findByText("Driver B private notice")).toBeInTheDocument();
    expect(screen.queryByText("Driver A private notice")).not.toBeInTheDocument();
    expect(client.getQueryData(["notifications", "driver-a", "list"])).toBeUndefined();
    view.unmount();
    expect(client.getQueryData(["notifications", "driver-b", "list"])).toBeUndefined();
  });
});
