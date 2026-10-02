import { beforeEach, expect, it, vi } from "vitest";
const mocks = vi.hoisted(() => ({ get: vi.fn(), guard: vi.fn() }));
vi.mock("@/lib/api/client", () => ({ createApiClient: () => ({ GET: mocks.get }) }));
vi.mock("@/lib/auth/session", () => ({ getSessionToken: async () => "staff-token" }));
vi.mock("@/lib/auth/current-user", () => ({ requireRole: mocks.guard }));
import { searchAdmin } from "./global-search-actions";
beforeEach(() => {
  mocks.get.mockReset();
  mocks.guard.mockReset();
});
it.each(["", "a", "x".repeat(121)])(
  "requires staff and avoids reads for invalid query %s",
  async (q) => {
    expect(await searchAdmin(q)).toEqual([]);
    expect(mocks.guard).toHaveBeenCalledWith("admin");
    expect(mocks.get).not.toHaveBeenCalled();
  },
);
it("groups named destinations, merges applicants by actual profile id, caps groups and uses server-filtered staff", async () => {
  mocks.get.mockImplementation(async (path: string) => {
    const items = path.endsWith("/drivers")
      ? Array.from({ length: 5 }, (_, i) => ({
          id: `d${i}`,
          full_name: `Driver ${i}`,
          email: `driver${i}@example.invalid`,
        }))
      : path.endsWith("/driver-applications")
        ? [
            { id: "a0", driver_profile_id: "d0", full_name: "Driver 0" },
            { id: "a1", driver_profile_id: null, full_name: "Applicant" },
          ]
        : path.endsWith("/vehicles")
          ? [{ id: "v", driver_profile_id: "d0", plate_number: "ABC-482-KJ" }]
          : path.endsWith("/campaigns")
            ? [{ id: "c", name: "Wuse campaign", organization: { name: "Example company" } }]
            : path.endsWith("/advertiser-organizations")
              ? [{ id: "o", name: "Example company" }]
              : [{ id: "human", full_name: "Ada", email: "ada@example.invalid" }];
    return { data: { items, total: items.length } };
  });
  const groups = await searchAdmin("  Ada  ");
  expect(groups.map((g) => g.name)).toEqual(["Drivers", "Cars", "Campaigns", "Companies", "Staff"]);
  expect(groups[0]!.items).toHaveLength(5);
  expect(groups[0]!.items.filter((h) => h.href === "/admin/drivers/d0")).toHaveLength(1);
  expect(groups[1]!.items[0]!.href).toBe("/admin/drivers/d0#cars");
  expect(groups[2]!.items[0]!.href).toBe("/admin/campaigns/c");
  expect(groups[3]!.items[0]!.href).toBe("/admin/advertisers/o");
  expect(groups[4]!.items.map((h) => h.name)).toEqual(["Ada"]);
  expect(mocks.get).toHaveBeenCalledWith("/api/v1/admin/users", {
    params: { query: { q: "Ada", limit: 5, offset: 0, role: "admin" } },
  });
});
it("preserves successful groups and marks a failed read unavailable", async () => {
  mocks.get.mockImplementation(async (path: string) => {
    if (path.endsWith("/vehicles")) throw new Error("down");
    return { data: { items: [], total: 0 } };
  });
  const groups = await searchAdmin("Ada");
  expect(groups[1]!.unavailable).toBe(true);
  expect(groups[0]!.unavailable).toBe(false);
});
it("does not fan out when staff authority is refused", async () => {
  mocks.guard.mockRejectedValue(new Error("forbidden"));
  await expect(searchAdmin("Ada")).rejects.toThrow("forbidden");
  expect(mocks.get).not.toHaveBeenCalled();
});
