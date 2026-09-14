import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const get = vi.hoisted(() => vi.fn());

vi.mock("@/lib/api/client", () => ({ createApiClient: () => ({ GET: get }) }));
vi.mock("@/lib/auth/session", () => ({ getSessionToken: vi.fn(async () => "token") }));

import AdminAuditPage from "./page";

const EVENT = {
  id: "00000000-0000-4000-8000-000000000001",
  created_at: "2026-09-13T10:00:00Z",
  actor_email: "admin@example.com",
  action: "stored_file.read",
  entity_type: "stored_file",
  entity_id: "00000000-0000-4000-8000-000000000002",
  metadata: {},
};

describe("AdminAuditPage filters", () => {
  beforeEach(() => get.mockReset());

  it("labels both exact-match filters and keeps their submitted values", async () => {
    get.mockResolvedValue({ data: { items: [EVENT], total: 1, limit: 50, offset: 0 } });

    render(
      await AdminAuditPage({
        searchParams: Promise.resolve({ action: "stored_file.read", entity_type: "stored_file" }),
      }),
    );

    const action = screen.getByLabelText("Action");
    const entityType = screen.getByLabelText("Entity type");
    expect(action).toHaveAttribute("name", "action");
    expect(action).toHaveValue("stored_file.read");
    expect(action).toHaveAttribute("placeholder", "Action, e.g. auth.login.succeeded");
    expect(entityType).toHaveAttribute("name", "entity_type");
    expect(entityType).toHaveValue("stored_file");
    expect(entityType).toHaveAttribute("placeholder", "Entity type");
    expect(action).toHaveAccessibleDescription(/exact action or entity type as shown in the table/);
    expect(entityType).toHaveAccessibleDescription(
      /exact action or entity type as shown in the table/,
    );
    expect(screen.getByRole("button", { name: "Filter" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Clear filters" })).toHaveAttribute(
      "href",
      "/admin/audit",
    );
    expect(
      screen.getByText(
        "Showing events with action “stored_file.read” and entity type “stored_file”.",
      ),
    ).toBeInTheDocument();
    expect(get).toHaveBeenCalledWith("/api/v1/admin/audit-events", {
      params: {
        query: { limit: 50, offset: 0, action: "stored_file.read", entity_type: "stored_file" },
      },
    });
  });

  it("explains an empty filtered result without a summary when unfiltered", async () => {
    get.mockResolvedValue({ data: { items: [], total: 0, limit: 50, offset: 0 } });

    render(await AdminAuditPage({ searchParams: Promise.resolve({ entity_type: "campaign" }) }));

    expect(screen.getByText("No events exactly match these filters.")).toBeInTheDocument();
    expect(screen.getByText("Showing events with entity type “campaign”.")).toBeInTheDocument();

    get.mockClear();
    const { container } = render(await AdminAuditPage({ searchParams: Promise.resolve({}) }));
    expect(container).toHaveTextContent("No matching events.");
    expect(container).not.toHaveTextContent("Showing events with");
    expect(get).toHaveBeenCalledWith("/api/v1/admin/audit-events", {
      params: { query: { limit: 50, offset: 0 } },
    });
  });
});
