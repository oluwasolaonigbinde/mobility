import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({ get: vi.fn() }));
vi.mock("@/lib/api/client", () => ({ createApiClient: () => ({ GET: mocks.get }) }));
vi.mock("@/lib/auth/session", () => ({ getSessionToken: async () => "token" }));
vi.mock("./users/user-status-menu", () => ({
  UserStatusMenu: () => <button>User actions</button>,
}));
vi.mock("./drivers/onboarding-menu", () => ({
  DriverOnboardingMenu: () => <button>Driver actions</button>,
}));
vi.mock("./vehicles/vehicle-status-menu", () => ({
  VehicleStatusMenu: () => <button>Vehicle actions</button>,
}));

import AdminUsersPage from "./settings/staff/page";
import AdminDriversPage from "./drivers/page";

const props = <T extends Record<string, string>>(params: T) => ({
  searchParams: Promise.resolve(params),
});

function enabledPageLinks() {
  return screen
    .getAllByRole("link")
    .map((link) => link.getAttribute("href") ?? "")
    .filter((href) => href !== "#" && href.includes("offset="));
}

describe("admin named discovery pages", () => {
  beforeEach(() => {
    mocks.get.mockReset();
  });

  it("staff: searches only staff and preserves the search in pagination", async () => {
    mocks.get.mockResolvedValue({
      data: {
        items: [
          {
            id: "u1",
            full_name: "Ada Okafor",
            email: "ada@example.com",
            role: "admin",
            status: "active",
          },
        ],
        total: 30,
      },
    });
    render(await AdminUsersPage(props({ q: "Okafor", role: "driver", offset: "25.7" })));
    expect(mocks.get).toHaveBeenCalledWith("/api/v1/admin/users", {
      params: { query: { limit: 25, offset: 25, q: "Okafor", role: "admin" } },
    });
    expect(screen.getByText("30 matching staff sign-ins")).toBeTruthy();
    expect(screen.getByText("Ada Okafor")).toBeTruthy();
    expect(screen.getByLabelText("Search staff")).toHaveValue("Okafor");
    expect(screen.getByRole("link", { name: "Add staff login" })).toHaveAttribute(
      "href",
      "/admin/settings/staff/new",
    );
    expect(screen.getByRole("link", { name: /Prev/ })).toHaveAttribute(
      "href",
      "/admin/settings/staff?q=Okafor&offset=0",
    );
  });
  it("staff: failed reads show one section failure without a field fallback", async () => {
    mocks.get.mockResolvedValue({ data: undefined });
    render(await AdminUsersPage(props({ role: "owner", offset: "-3" })));
    expect(mocks.get).toHaveBeenCalledWith("/api/v1/admin/users", {
      params: { query: { limit: 25, offset: 0, q: undefined, role: "admin" } },
    });
    expect(screen.getAllByRole("alert")).toHaveLength(1);
    expect(screen.getByRole("alert")).toHaveTextContent("Couldn't load this section — try again");
    expect(screen.queryByText(/count unavailable/)).toBeNull();
  });

  it("drivers: searches the chosen status and preserves the search in pagination", async () => {
    mocks.get.mockImplementation(async (path: string) => ({
      data: path.endsWith("/drivers")
        ? {
            items: [
              {
                id: "d1",
                full_name: "Chinedu Okafor",
                phone: "+2348039876543",
                service_city: "Abuja",
                onboarding_status: "active",
              },
            ],
            total: 26,
          }
        : { items: [{ plate_number: "ABC-123-XY" }], total: 1 },
    }));
    render(await AdminDriversPage(props({ q: "Okafor", tab: "active" })));
    expect(mocks.get).toHaveBeenCalledWith("/api/v1/admin/drivers", {
      params: { query: { limit: 25, offset: 0, q: "Okafor", onboarding_status: "active" } },
    });
    expect(screen.getByText("26 matching driver profiles")).toBeTruthy();
    expect(screen.getByRole("link", { name: /Chinedu Okafor/ })).toHaveAttribute(
      "href",
      "/admin/drivers/d1",
    );
    expect(screen.getByText("ABC-123-XY")).toBeTruthy();
    expect(enabledPageLinks()).toEqual([
      "/admin/drivers?tab=active&source=profiles&q=Okafor&history=false&offset=25",
    ]);
  });
  it("drivers: a failed car read is unavailable rather than a claim of no cars", async () => {
    mocks.get.mockImplementation(async (path: string) => {
      if (path.endsWith("/vehicles")) throw new Error("offline");
      return {
        data: { items: [{ id: "d1", full_name: "Ada", onboarding_status: "active" }], total: 1 },
      };
    });
    render(await AdminDriversPage(props({ tab: "active" })));
    expect(screen.getByText("Couldn't load this section — try again")).toBeTruthy();
    expect(screen.queryByText("No cars recorded")).toBeNull();
  });
  it("cars: plate results open the actual driver's Cars section", async () => {
    mocks.get.mockResolvedValue({
      data: {
        items: [
          {
            id: "car",
            driver_profile_id: "driver",
            driver_profile: { full_name: "Ada", phone: "+2348031234567" },
            plate_number: "ABC-123-XY",
            status: "active",
          },
        ],
        total: 51,
      },
    });
    render(
      await AdminDriversPage(props({ tab: "active", source: "cars", q: "ABC", offset: "25" })),
    );
    expect(mocks.get).toHaveBeenCalledExactlyOnceWith("/api/v1/admin/vehicles", {
      params: { query: { limit: 25, offset: 25, q: "ABC" } },
    });
    expect(screen.getByRole("link", { name: /Ada.*ABC-123-XY/ })).toHaveAttribute(
      "href",
      "/admin/drivers/driver#cars",
    );
    expect(enabledPageLinks()).toHaveLength(2);
  });
  it("applicants: preserves the history filter and keeps document contents off the work list", async () => {
    mocks.get.mockResolvedValue({
      data: {
        items: [
          {
            id: "application",
            driver_profile_id: "driver",
            full_name: "Ada Applicant",
            status: "pending",
            person_payee: { status: "pending_review", masked_nin: "*******8901" },
          },
        ],
        total: 1,
      },
    });
    render(await AdminDriversPage(props({ history: "true", source: "applications" })));
    expect(mocks.get).toHaveBeenCalledWith("/api/v1/admin/driver-applications", {
      params: { query: { limit: 25, offset: 0, q: undefined, history: true } },
    });
    expect(screen.getByRole("link", { name: /Ada Applicant/ })).toHaveAttribute(
      "href",
      "/admin/drivers/driver?application=application",
    );
    expect(screen.queryByText(/8901/)).toBeNull();
    expect(screen.queryByRole("button", { name: "Approve" })).toBeNull();
  });
  it("drivers: failed reads do not turn into an empty list", async () => {
    mocks.get.mockRejectedValue(new Error("offline"));
    render(await AdminDriversPage(props({})));
    expect(screen.getAllByRole("alert")).toHaveLength(2);
    expect(screen.queryByText(/No matching drivers/)).toBeNull();
  });
});

it("Applicants includes applications and other pending profiles with independent pages", async () => {
  mocks.get.mockImplementation(async (path: string) => ({
    data: path.endsWith("/driver-applications")
      ? { items: [{ id: "a", full_name: "New applicant", status: "pending" }], total: 26 }
      : path.endsWith("/drivers")
        ? {
            items: [{ id: "d", full_name: "Pending profile", onboarding_status: "pending" }],
            total: 30,
          }
        : { items: [], total: 0 },
  }));
  render(await AdminDriversPage(props({ applications_offset: "25" })));
  expect(screen.getByRole("link", { name: /New applicant/ })).toBeTruthy();
  expect(screen.getByRole("link", { name: /Pending profile/ })).toBeTruthy();
  expect(mocks.get).toHaveBeenCalledWith("/api/v1/admin/drivers", {
    params: { query: { limit: 25, offset: 0, q: undefined, onboarding_status: "pending" } },
  });
  expect(screen.getAllByRole("link", { name: "Next →" })[1]).toHaveAttribute(
    "href",
    "/admin/drivers?applications_offset=25&tab=applicants&profiles_offset=25",
  );
});
