import { beforeEach, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
const mocks = vi.hoisted(() => ({ post: vi.fn(), redirect: vi.fn(), requireRole: vi.fn() }));
vi.mock("next/cache", () => ({ revalidatePath: vi.fn() }));
vi.mock("next/navigation", () => ({ redirect: mocks.redirect }));
vi.mock("@/lib/auth/session", () => ({ getSessionToken: async () => "token" }));
vi.mock("@/lib/auth/current-user", () => ({ requireRole: mocks.requireRole }));
vi.mock("@/lib/api/client", () => ({ createApiClient: () => ({ POST: mocks.post }) }));
import { createCompanyAction } from "./actions";
import { CreateCompanyForm } from "./create-company-form";
beforeEach(() => {
  vi.clearAllMocks();
});
it("creates the company and sends its invite in one request, without a password or owner", async () => {
  mocks.post.mockResolvedValue({ data: { organization: { id: "new-company" } } });
  const form = new FormData();
  form.set("name", "Test company");
  form.set("email", " INVITED@EXAMPLE.COM ");
  await createCompanyAction({}, form);
  expect(mocks.requireRole).toHaveBeenCalledWith("admin");
  expect(mocks.post).toHaveBeenCalledExactlyOnceWith("/api/v1/admin/advertiser-organizations", {
    body: { name: "Test company", email: "invited@example.com" },
  });
  expect(mocks.redirect).toHaveBeenCalledWith("/admin/advertisers/new-company#people");
});
it("asks for a login email and makes the send explicit, without temporary passwords", () => {
  render(<CreateCompanyForm />);
  expect(screen.getByLabelText("Login email")).toBeRequired();
  expect(screen.queryByLabelText("Temporary password")).toBeNull();
  expect(screen.getByRole("button", { name: "Add company and send invite" })).toBeInTheDocument();
});
it("does not retry a partial company or redirect after an unconfirmed response", async () => {
  mocks.post.mockResolvedValue({ data: undefined });
  const form = new FormData();
  form.set("name", "Test");
  form.set("email", "test@example.com");
  expect((await createCompanyAction({}, form)).error).toContain("Check the company list");
  expect(mocks.post).toHaveBeenCalledOnce();
  expect(mocks.redirect).not.toHaveBeenCalled();
});
