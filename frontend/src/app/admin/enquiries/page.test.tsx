import { render, screen } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
const mocks = vi.hoisted(() => ({ read: vi.fn(), role: vi.fn() }));
vi.mock("@/lib/api/client", () => ({ createApiClient: () => ({}) }));
vi.mock("@/lib/api/audit-batch2", () => ({ readStaffEnquiries: mocks.read }));
vi.mock("@/lib/auth/current-user", () => ({ requireRole: mocks.role }));
vi.mock("@/lib/auth/session", () => ({ getSessionToken: async () => "session" }));
import EnquiriesPage from "./page";
beforeEach(() => {
  vi.resetAllMocks();
  mocks.read.mockResolvedValue({ data: { items: [], total: 0 } });
});
it("shows a truthful empty enquiry list", async () => {
  render(await EnquiriesPage({ searchParams: Promise.resolve({}) }));
  expect(mocks.role).toHaveBeenCalledWith("admin");
  expect(
    screen.getByText("No new enquiries. Website quote requests will appear here."),
  ).toBeInTheDocument();
});
it("keeps failed reads separate from empty lists", async () => {
  mocks.read.mockRejectedValue(new Error("offline"));
  render(await EnquiriesPage({ searchParams: Promise.resolve({}) }));
  expect(screen.getByRole("alert")).toBeInTheDocument();
  expect(screen.queryByText(/No new enquiries/)).toBeNull();
});
it("preserves the human converted tab, bounded search and pagination", async () => {
  mocks.read.mockResolvedValue({
    data: {
      items: [
        {
          id: "enquiry",
          company: "<script>company</script>",
          contact_name: "Ada",
          email: "ada@example.com",
          created_at: "2026-10-18T12:00:00Z",
        },
      ],
      total: 30,
    },
  });
  const { container } = render(
    await EnquiriesPage({
      searchParams: Promise.resolve({ status: "converted", q: "  Company  ", offset: "25" }),
    }),
  );
  expect(mocks.read).toHaveBeenCalledWith(expect.anything(), {
    status: "converted",
    q: "Company",
    offset: 25,
    limit: 25,
  });
  expect(screen.getByRole("link", { name: /<script>company/ })).toHaveAttribute(
    "href",
    "/admin/enquiries/enquiry",
  );
  expect(container.querySelector("script")).toBeNull();
  expect(screen.getByRole("link", { name: "Advertiser created" })).toHaveAttribute(
    "aria-current",
    "page",
  );
});
