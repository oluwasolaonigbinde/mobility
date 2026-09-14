import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
const { requireRole } = vi.hoisted(() => ({ requireRole: vi.fn() }));
vi.mock("@/lib/auth/current-user", () => ({ requireRole }));
vi.mock("@/components/shell/app-shell", () => ({
  AppShell: ({ children }: { children: React.ReactNode }) => <main>{children}</main>,
}));
import AdvertiserLayout from "./layout";

describe("advertiser layout", () => {
  it.each(["demo@example.com", "normal@example.com"])(
    "renders the workspace without demonstration presentation for %s",
    async (email) => {
      requireRole.mockResolvedValue({
        user: { role: "advertiser", email },
        advertiser_organization: { id: "org-1" },
      });
      render(await AdvertiserLayout({ children: <p>Healthy page</p> }));
      expect(requireRole).toHaveBeenCalledWith("advertiser");
      expect(screen.getByText("Healthy page")).toBeInTheDocument();
      expect(document.body).not.toHaveTextContent(/demo|synthetic/i);
    },
  );
});
