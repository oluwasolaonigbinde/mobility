import { render, screen } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
const get = vi.hoisted(() => vi.fn());
vi.mock("@/lib/api/client", () => ({ createApiClient: () => ({ GET: get }) }));
vi.mock("@/lib/auth/session", () => ({ getSessionToken: async () => "token" }));
import AdminAuditPage from "./page";
const event = {
  id: "event-id",
  created_at: "2026-10-18T22:30:00Z",
  actor_email: "staff@example.com",
  action: "auth.login.succeeded",
  entity_type: "user",
  entity_id: "private-id",
  metadata: { private_field: "private value" },
};
beforeEach(() => {
  vi.resetAllMocks();
});
it("uses human filters with exact API values, and displays actor/action/date without technical payloads", async () => {
  get.mockResolvedValue({ data: { items: [event], total: 1 } });
  const { container } = render(
    await AdminAuditPage({
      searchParams: Promise.resolve({
        action: "auth.login.succeeded",
        entity_type: "user",
        offset: "50",
      }),
    }),
  );
  expect(screen.getByRole("combobox", { name: "Activity" })).toHaveValue("auth.login.succeeded");
  expect(screen.getByRole("combobox", { name: "About" })).toHaveValue("user");
  expect(screen.getByRole("option", { name: "Signed in" })).toBeInTheDocument();
  expect(screen.getByRole("cell", { name: "Signed in" })).toBeInTheDocument();
  expect(screen.getByRole("cell", { name: "staff@example.com" })).toBeInTheDocument();
  expect(container).not.toHaveTextContent(
    /private-id|private_field|private value|auth.login.succeeded|Recorded activity|Technical reference/,
  );
  expect(container.querySelector('input[name="offset"]')).toBeNull();
  expect(get).toHaveBeenCalledWith("/api/v1/admin/audit-events", {
    params: {
      query: { limit: 50, offset: 50, action: "auth.login.succeeded", entity_type: "user" },
    },
  });
});
it("preserves unknown URL filters in a human-labelled selected option", async () => {
  get.mockResolvedValue({ data: { items: [], total: 0 } });
  render(
    await AdminAuditPage({
      searchParams: Promise.resolve({ action: "stored_file.read", entity_type: "new_type" }),
    }),
  );
  expect(screen.getByRole("combobox", { name: "Activity" })).toHaveValue("stored_file.read");
  expect(screen.getByRole("combobox", { name: "About" })).toHaveValue("new_type");
  expect(screen.getByRole("option", { name: "Stored file read" })).toBeInTheDocument();
  expect(screen.getByRole("option", { name: "Selected records" })).toBeInTheDocument();
  expect(screen.getByText("No activity matches these filters.")).toBeInTheDocument();
});
it("keeps genuine empty history separate from unavailable history", async () => {
  get.mockResolvedValue({ data: { items: [], total: 0 } });
  const empty = render(await AdminAuditPage({ searchParams: Promise.resolve({}) }));
  expect(screen.getByText("No matching events.")).toBeInTheDocument();
  empty.unmount();
  get.mockRejectedValue(new Error("offline"));
  render(await AdminAuditPage({ searchParams: Promise.resolve({}) }));
  expect(screen.getAllByRole("alert")).toHaveLength(1);
  expect(screen.queryByText("No matching events.")).toBeNull();
});
