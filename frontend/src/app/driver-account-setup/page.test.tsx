import { render, screen } from "@testing-library/react";
import { renderToString } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

// REQ-316 F8: setup links carry the token in the fragment, captured on the client, so each
// test opens the page at a URL and loads fresh page-memory state.
async function openPage(url: string) {
  window.history.replaceState(null, "", url);
  vi.resetModules();
  return import("./page");
}

describe("DriverAccountSetupPage", () => {
  it("presents an authorized one-use setup action without implying activation by the form", async () => {
    const { default: DriverAccountSetupPage, metadata } = await openPage(
      "/driver-account-setup#token=private-one-use-token",
    );
    render(<DriverAccountSetupPage />);

    expect(window.location.hash).toBe("");
    expect(screen.getByRole("heading", { name: "Set up your driver account" })).toBeInTheDocument();
    expect(
      screen.getByText("Choose a password to finish setting up your driver account."),
    ).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: "Set password" })).toBeInTheDocument();
    expect(document.querySelector("input[name=token]")).toHaveValue("private-one-use-token");
    expect(screen.queryByText("private-one-use-token")).not.toBeInTheDocument();
    expect(metadata.referrer).toBe("no-referrer");
  });

  it.each(["/driver-account-setup", "/driver-account-setup?token=query-token"])(
    "fails closed when the setup authority is missing: %s",
    async (url) => {
      const { default: DriverAccountSetupPage } = await openPage(url);
      render(<DriverAccountSetupPage />);

      expect(await screen.findByRole("alert")).toHaveTextContent(
        "This link is incomplete. Ask Terrax Media for a new account setup email.",
      );
      expect(screen.queryByRole("button", { name: "Set password" })).not.toBeInTheDocument();
    },
  );

  it("renders a neutral loading state on the server, never the incomplete-link alert", async () => {
    const { default: DriverAccountSetupPage } = await openPage(
      "/driver-account-setup#token=private-one-use-token",
    );
    const html = renderToString(<DriverAccountSetupPage />);
    expect(html).toContain("Opening your setup link");
    expect(html).not.toContain("incomplete");
    expect(html).not.toContain("private-one-use-token");
  });
});
