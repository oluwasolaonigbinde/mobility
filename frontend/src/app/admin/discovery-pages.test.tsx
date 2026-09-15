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

import AdminUsersPage from "./users/page";
import AdminDriversPage from "./drivers/page";
import AdminVehiclesPage from "./vehicles/page";

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
  beforeEach(() => mocks.get.mockReset());

  it("users: passes search and role, and keeps both across role filters and pages", async () => {
    mocks.get.mockResolvedValue({
      data: {
        items: [
          {
            id: "u1",
            full_name: "Ada Okafor",
            email: "ada@example.com",
            role: "driver",
            status: "active",
          },
        ],
        total: 30,
      },
    });
    render(await AdminUsersPage(props({ q: "Okafor", role: "driver", offset: "25.7" })));
    expect(mocks.get).toHaveBeenCalledWith("/api/v1/admin/users", {
      params: { query: { limit: 25, offset: 25, q: "Okafor", role: "driver" } },
    });
    expect(screen.getByText("30 matching accounts")).toBeTruthy();
    expect(screen.getByText("Ada Okafor")).toBeTruthy();
    expect(screen.getByLabelText("Search this work list")).toHaveValue("Okafor");
    expect(document.querySelector('input[type="hidden"][name="role"]')).toHaveAttribute(
      "value",
      "driver",
    );
    expect(screen.getByRole("link", { name: "All" })).toHaveAttribute(
      "href",
      "/admin/users?q=Okafor",
    );
    expect(screen.getByRole("link", { name: "admin" })).toHaveAttribute(
      "href",
      "/admin/users?role=admin&q=Okafor",
    );
    expect(screen.getByRole("link", { name: /Prev/ })).toHaveAttribute(
      "href",
      "/admin/users?role=driver&q=Okafor",
    );
  });

  it("users: ignores an unknown role and reports an unavailable list distinctly", async () => {
    mocks.get.mockResolvedValue({ data: undefined });
    render(await AdminUsersPage(props({ role: "owner", offset: "-3" })));
    expect(mocks.get).toHaveBeenCalledWith("/api/v1/admin/users", {
      params: { query: { limit: 25, offset: 0, q: undefined } },
    });
    expect(screen.getByText("Account count unavailable")).toBeTruthy();
    expect(screen.getByRole("alert")).toHaveTextContent("No empty or complete result");
    expect(screen.getByRole("link", { name: "All" })).toHaveAttribute("href", "/admin/users");
  });

  it("users: labels a single match without a plural", async () => {
    mocks.get.mockResolvedValue({ data: { items: [], total: 1 } });
    render(await AdminUsersPage(props({})));
    expect(screen.getByText("1 matching account")).toBeTruthy();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("drivers: searches named profiles and keeps the search in pagination", async () => {
    mocks.get.mockResolvedValue({
      data: {
        items: [
          {
            id: "d1",
            full_name: "Chinedu Okafor",
            email: "chinedu@example.com",
            license_number: null,
            service_city: "Abuja",
            onboarding_status: "active",
          },
        ],
        total: 26,
      },
    });
    render(await AdminDriversPage(props({ q: "Okafor" })));
    expect(mocks.get).toHaveBeenCalledWith("/api/v1/admin/drivers", {
      params: { query: { limit: 25, offset: 0, q: "Okafor" } },
    });
    expect(screen.getByText("26 matching driver profiles")).toBeTruthy();
    expect(screen.getByText("Chinedu Okafor")).toBeTruthy();
    expect(enabledPageLinks()).toEqual(["/admin/drivers?q=Okafor&offset=25"]);
  });

  it("drivers: reports an unavailable list and a single match", async () => {
    mocks.get.mockRejectedValueOnce(new Error("network"));
    const { unmount } = render(await AdminDriversPage(props({})));
    expect(screen.getByText("Driver count unavailable")).toBeTruthy();
    expect(screen.getByRole("alert")).toBeTruthy();
    unmount();
    mocks.get.mockResolvedValue({ data: { items: [], total: 1 } });
    render(await AdminDriversPage(props({})));
    expect(screen.getByText("1 matching driver profile")).toBeTruthy();
  });

  it("vehicles: searches plates and describes partial vehicle details", async () => {
    mocks.get.mockResolvedValue({
      data: {
        items: [
          {
            id: "v1",
            plate_number: "DEMO-001",
            year: 2021,
            make: "Toyota",
            model: null,
            color: "White",
            vehicle_type: "car",
            status: "active",
          },
          {
            id: "v2",
            plate_number: "DEMO-002",
            year: null,
            make: null,
            model: null,
            color: null,
            vehicle_type: "van",
            status: "inactive",
          },
        ],
        total: 51,
      },
    });
    render(await AdminVehiclesPage(props({ q: "DEMO", offset: "25" })));
    expect(mocks.get).toHaveBeenCalledWith("/api/v1/admin/vehicles", {
      params: { query: { limit: 25, offset: 25, q: "DEMO" } },
    });
    expect(screen.getByText("51 matching vehicles")).toBeTruthy();
    expect(screen.getByText("2021 Toyota White")).toBeTruthy();
    expect(screen.getByText("—")).toBeTruthy();
    expect(enabledPageLinks()).toEqual([
      "/admin/vehicles?q=DEMO&offset=0",
      "/admin/vehicles?q=DEMO&offset=50",
    ]);
  });

  it("vehicles: reports an unavailable list and a single match", async () => {
    mocks.get.mockResolvedValueOnce({ data: undefined });
    const { unmount } = render(await AdminVehiclesPage(props({})));
    expect(screen.getByText("Vehicle count unavailable")).toBeTruthy();
    expect(screen.getByRole("alert")).toBeTruthy();
    unmount();
    mocks.get.mockResolvedValue({ data: { items: [], total: 1 } });
    render(await AdminVehiclesPage(props({})));
    expect(screen.getByText("1 matching vehicle")).toBeTruthy();
  });
});
