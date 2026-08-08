import { describe, expect, it } from "vitest";
import { demoLoginRoleFromPath } from "./demo-role";

describe("demoLoginRoleFromPath", () => {
  it.each([
    ["/advertiser", "advertiser"],
    ["/advertiser/campaigns", "advertiser"],
    ["/driver", "driver"],
    ["/driver/assignments", "driver"],
    ["/admin", "admin"],
    ["/admin/users", "admin"],
  ] as const)("maps %s to %s", (from, role) => {
    expect(demoLoginRoleFromPath(from)).toBe(role);
  });

  it.each([
    undefined,
    "",
    ["/admin", "/driver"],
    "/administrator",
    "/admin-evil",
    "//admin",
    "https://example.com/admin",
    "\\admin",
    "%2Fadmin",
    "%252Fadmin",
  ])("defaults unsafe or ambiguous value %j to advertiser", (from) => {
    expect(demoLoginRoleFromPath(from)).toBe("advertiser");
  });
});
