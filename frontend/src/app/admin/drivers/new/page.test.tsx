import { render, screen } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";

const get = vi.hoisted(() => vi.fn());
vi.mock("@/lib/api/client", () => ({ createApiClient: () => ({ GET: get }) }));
vi.mock("@/lib/auth/session", () => ({ getSessionToken: async () => "token" }));
vi.mock("../../users/new/create-user-form", () => ({ CreateUserForm: () => null }));
vi.mock("../../fleet-actions", () => ({ createDriverProfileAction: vi.fn() }));

import NewDriverProfilePage from "./page";

beforeEach(() => get.mockReset());

it("requests only driver logins without profiles and offers the returned login", async () => {
  get.mockResolvedValue({
    data: { items: [{ id: "driver", full_name: "Ada Driver", email: "ada@example.test" }] },
  });
  render(await NewDriverProfilePage());
  expect(get).toHaveBeenCalledWith("/api/v1/admin/users", {
    params: { query: { role: "driver", without_driver_profile: true, limit: 100 } },
  });
  expect(screen.getByLabelText("Driver user")).toBeInTheDocument();
  expect(screen.getByRole("option", { name: /Ada Driver.*ada@example.test/ })).toHaveValue(
    "driver",
  );
});

it("explains when all driver logins already have profiles", async () => {
  get.mockResolvedValue({ data: { items: [] } });
  render(await NewDriverProfilePage());
  expect(screen.getByText("Every driver login already has a profile.")).toBeVisible();
  expect(screen.queryByLabelText("Driver user")).toBeNull();
  expect(screen.getByRole("heading", { name: "Create driver login" })).toBeVisible();
});
