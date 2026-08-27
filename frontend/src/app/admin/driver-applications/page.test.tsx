import { render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const get = vi.hoisted(() => vi.fn());

vi.mock("@/lib/api/client", () => ({ createApiClient: () => ({ GET: get }) }));
vi.mock("@/lib/auth/session", () => ({ getSessionToken: vi.fn(async () => "admin-token") }));

import AdminDriverApplicationsPage from "./page";

const APPLICATION_ID = "00000000-0000-4000-8000-00000000000a";

describe("AdminDriverApplicationsPage", () => {
  beforeEach(() => get.mockReset());

  it("renders the sanitized pending queue and pagination inputs", async () => {
    get.mockResolvedValue({
      data: {
        items: [
          {
            id: APPLICATION_ID,
            user_id: "00000000-0000-4000-8000-00000000000b",
            driver_profile_id: "00000000-0000-4000-8000-00000000000c",
            status: "pending",
            email: "driver@example.com",
            full_name: "New Driver",
            phone: "+2348000000000",
            service_city: "Lagos",
            country_code: "NG",
            created_at: "2026-08-25T10:00:00Z",
            updated_at: "2026-08-25T10:00:00Z",
            person_payee: {
              status: "pending_review",
              submission_id: "00000000-0000-4000-8000-00000000000d",
              version: 1,
              masked_nin: "*******8901",
              bank_account_verified: true,
              bank_account_version_id: "00000000-0000-4000-8000-00000000000e",
              document_file_ids: {
                driver_license: "00000000-0000-4000-8000-00000000000f",
                driver_photo: "00000000-0000-4000-8000-000000000010",
                signed_agreement: "00000000-0000-4000-8000-000000000011",
              },
            },
          },
        ],
        total: 26,
        limit: 25,
        offset: 0,
      },
    });

    render(await AdminDriverApplicationsPage({ searchParams: Promise.resolve({}) }));

    const row = screen.getByText("New Driver").closest("tr");
    if (!row) throw new Error("expected application row");
    expect(within(row).getByText("driver@example.com")).toBeInTheDocument();
    expect(within(row).getByText("Lagos · NG")).toBeInTheDocument();
    expect(within(row).getByText("pending")).toBeInTheDocument();
    expect(within(row).getByText("pending review")).toBeInTheDocument();
    expect(within(row).getByText("v1 · *******8901")).toBeInTheDocument();
    expect(within(row).getByRole("button", { name: "Approve" })).toBeInTheDocument();
    expect(within(row).getByRole("button", { name: "Reveal NIN" })).toBeInTheDocument();
    expect(within(row).getByRole("button", { name: "Reveal account" })).toBeInTheDocument();
    expect(within(row).getByRole("button", { name: "Review driver license" })).toBeInTheDocument();
    expect(within(row).getByText("Exact account version is payout-verified.")).toBeInTheDocument();
    expect(screen.queryByText(/password|reference_sha|ratelimit/i)).not.toBeInTheDocument();
    expect(get).toHaveBeenCalledWith("/api/v1/admin/driver-applications", {
      params: { query: { limit: 25, offset: 0 } },
    });
    expect(screen.getByRole("navigation", { name: "Pagination" })).toBeInTheDocument();
  });

  it("renders the empty queue without extra reads", async () => {
    get.mockResolvedValue({ data: { items: [], total: 0, limit: 25, offset: 0 } });

    render(await AdminDriverApplicationsPage({ searchParams: Promise.resolve({}) }));

    expect(screen.getByText("No pending driver applications")).toBeInTheDocument();
    expect(get).toHaveBeenCalledOnce();
  });
});
