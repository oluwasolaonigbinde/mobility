import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
const mocks = vi.hoisted(() => ({ get: vi.fn(), form: vi.fn() }));
vi.mock("@/lib/api/client", () => ({ createApiClient: () => ({ GET: mocks.get }) }));
vi.mock("@/lib/auth/session", () => ({ getSessionToken: vi.fn(async () => "token") }));
vi.mock("../../traffic/profile-form", () => ({
  ProfileForm: ({ profile }: { profile: { name: string } | null }) => {
    mocks.form(profile);
    return <div>Editing {profile?.name ?? "new"}</div>;
  },
}));
import Page from "./page";
const profile = { id: "default", name: "Default estimate", revision: 2, is_default: true };
describe("Reach estimates selection", () => {
  beforeEach(() => vi.resetAllMocks());
  it("loads exact off-page selected estimate and preserves selection in pagination", async () => {
    mocks.get
      .mockResolvedValueOnce({ data: { items: [profile], total: 101 } })
      .mockResolvedValueOnce({ data: { ...profile, id: "selected", name: "Selected estimate" } });
    render(await Page({ searchParams: Promise.resolve({ profile: "selected", offset: "50" }) }));
    expect(mocks.get).toHaveBeenLastCalledWith(
      "/api/v1/admin/traffic-density-profiles/{profile_id}",
      { params: { path: { profile_id: "selected" } } },
    );
    expect(screen.getByText("Editing Selected estimate")).toBeVisible();
    expect(screen.getByRole("link", { name: "Next →" })).toHaveAttribute(
      "href",
      "/admin/settings/reach?profile=selected&offset=100",
    );
  });
  it.each([undefined, { ...profile, id: "wrong" }])(
    "never edits the default after selected lookup fails or mismatches",
    async (detail) => {
      mocks.get
        .mockResolvedValueOnce({ data: { items: [profile], total: 1 } })
        .mockResolvedValueOnce({ data: detail });
      render(await Page({ searchParams: Promise.resolve({ profile: "selected" }) }));
      expect(screen.getAllByRole("alert")).toHaveLength(1);
      expect(mocks.form).not.toHaveBeenCalled();
    },
  );
  it("uses a new form only when new is explicitly selected", async () => {
    mocks.get.mockResolvedValue({ data: { items: [profile], total: 1 } });
    render(await Page({ searchParams: Promise.resolve({ profile: "new" }) }));
    expect(screen.getByText("Editing new")).toBeVisible();
    expect(mocks.get).toHaveBeenCalledTimes(1);
  });
});
