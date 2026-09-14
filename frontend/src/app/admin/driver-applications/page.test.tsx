import { render, screen } from "@testing-library/react";
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
            vehicle: {
              status: "pending_review",
              vehicle_id: "00000000-0000-4000-8000-000000000012",
              submission_id: "00000000-0000-4000-8000-000000000013",
              version: 1,
              plate_number: "ABC-123-XY",
              document_file_ids: {
                registration: "00000000-0000-4000-8000-000000000014",
                insurance: "00000000-0000-4000-8000-000000000015",
                vehicle_photo: "00000000-0000-4000-8000-000000000016",
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

    expect(screen.getByRole("link", { name: /New Driver/ })).toHaveAttribute(
      "href",
      `/admin/driver-applications/${APPLICATION_ID}`,
    );
    expect(screen.getByText(/driver@example.com/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Reveal NIN" })).not.toBeInTheDocument();
    expect(screen.queryByText(/8901/)).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Approve" })).not.toBeInTheDocument();
    expect(screen.queryByText(/password|reference_sha|ratelimit/i)).not.toBeInTheDocument();
    expect(get).toHaveBeenCalledWith("/api/v1/admin/driver-applications", {
      params: { query: { limit: 25, offset: 0, q: undefined, history: false } },
    });
    expect(screen.getByRole("navigation", { name: "Pagination" })).toBeInTheDocument();
  });

  it("renders the empty queue without extra reads", async () => {
    get.mockResolvedValue({ data: { items: [], total: 0, limit: 25, offset: 0 } });

    render(await AdminDriverApplicationsPage({ searchParams: Promise.resolve({}) }));

    expect(screen.getByText(/No matching applications/)).toBeInTheDocument();
    expect(get).toHaveBeenCalledOnce();
  });
});
