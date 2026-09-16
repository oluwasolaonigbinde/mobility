import { describe, expect, it, vi } from "vitest";

const redirect = vi.hoisted(() => vi.fn());
vi.mock("next/navigation", () => ({ redirect }));

import LandingCompatibilityPage from "./page";

describe("former landing URL", () => {
  it("redirects to the canonical public root", () => {
    LandingCompatibilityPage();
    expect(redirect).toHaveBeenCalledWith("/");
  });
});
