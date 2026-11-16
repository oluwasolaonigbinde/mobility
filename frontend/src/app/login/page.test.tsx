import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  user: vi.fn(),
  demo: { enabled: false },
  form: vi.fn(),
}));
vi.mock("@/lib/auth/current-user", () => ({
  getCurrentUser: mocks.user,
  roleHome: (role: string) => `/${role}`,
}));
vi.mock("@/lib/env", () => ({ env: () => ({ DEMO_LOGIN_ENABLED: mocks.demo.enabled }) }));
vi.mock("next/navigation", () => ({
  redirect: (path: string) => {
    throw new Error(`redirect:${path}`);
  },
}));
vi.mock("./login-form", () => ({
  LoginForm: (props: { demoLoginRole?: string; from?: string }) => {
    mocks.form(props);
    return <form aria-label="Sign-in form" />;
  },
}));

import LoginPage from "./page";

const open = async (from?: string | string[]) =>
  render(await LoginPage({ searchParams: Promise.resolve({ from }) }));

beforeEach(() => {
  mocks.user.mockReset().mockResolvedValue(null);
  mocks.form.mockReset();
  mocks.demo.enabled = false;
});

describe("sign-in page", () => {
  it("sends a signed-in user to their own home", async () => {
    mocks.user.mockResolvedValue({ user: { role: "driver" } });
    await expect(open()).rejects.toThrow("redirect:/driver");
  });

  it("shows the sign-in heading and form over a hidden, decorative backdrop", async () => {
    const { container } = await open("/advertiser/billing");

    expect(screen.getByRole("heading", { name: "Sign in" })).toBeInTheDocument();
    expect(screen.getByText("Welcome to Cardvert")).toBeInTheDocument();
    expect(mocks.form).toHaveBeenCalledWith({
      demoLoginRole: undefined,
      from: "/advertiser/billing",
    });

    const backdrop = container.querySelector("main > div[aria-hidden]");
    expect(backdrop).not.toBeNull();
    expect(backdrop?.querySelector("a, button, input")).toBeNull();
  });

  it("drives every vehicle along a drawn road, both ways, and stops them for reduced motion", async () => {
    const { container } = await open();

    const roads = new Set([...container.querySelectorAll("path[id]")].map((path) => `#${path.id}`));
    const motions = [...container.querySelectorAll("animateMotion")];
    expect(motions).toHaveLength(8);
    for (const motion of motions) {
      expect(roads.has(motion.querySelector("mpath")?.getAttribute("href") ?? "")).toBe(true);
      expect(motion.getAttribute("rotate")).toBe("auto");
    }
    expect(new Set(motions.map((m) => m.getAttribute("keyPoints")))).toEqual(
      new Set(["0;1", "1;0"]),
    );
    expect(motions[0]?.closest("g.motion-reduce\\:hidden")).not.toBeNull();
    expect(container.querySelector("path.motion-safe\\:hidden")).not.toBeNull();
  });

  it("offers the demo shortcut only when demo sign-in is switched on", async () => {
    mocks.demo.enabled = true;
    await open(["/admin", "/driver"]);
    expect(mocks.form).toHaveBeenLastCalledWith({ demoLoginRole: "advertiser", from: undefined });

    await open("/admin/campaigns");
    expect(mocks.form).toHaveBeenLastCalledWith({
      demoLoginRole: "admin",
      from: "/admin/campaigns",
    });
  });
});
