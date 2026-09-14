import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { DataUnavailable } from "./data-unavailable";

describe("section unavailable presentation", () => {
  it.each(["operational", "protocol"] as const)(
    "offers a native full-navigation retry for transient %s failures",
    (reason) => {
      render(
        <DataUnavailable
          title="Campaign section unavailable"
          reason={reason}
          retryHref="/advertiser/campaigns/one"
        />,
      );
      expect(
        screen.getByRole("status", { name: "Campaign section unavailable" }),
      ).toBeInTheDocument();
      expect(screen.getByText("This couldn't be loaded right now.")).toBeInTheDocument();
      const retry = screen.getByRole("link", { name: "Try again" });
      expect(retry).toHaveAttribute("href", "/advertiser/campaigns/one");
      expect(retry).not.toHaveAttribute("data-nextjs-router");
    },
  );
  it.each([
    ["gated", "Available once privacy approval for campaign results is complete."],
    ["forbidden", "Your account doesn't have access to this."],
    ["missing", "This information couldn't be found."],
  ] as const)("explains %s concisely without a pointless retry", (reason, detail) => {
    render(
      <DataUnavailable
        title="Analytics unavailable"
        reason={reason}
        retryHref="/advertiser"
        className="mt-6"
      />,
    );
    expect(screen.getByRole("status")).toHaveClass("mt-6");
    expect(screen.getByText(detail)).toBeInTheDocument();
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
    expect(document.body).not.toHaveTextContent(/sample|demo|synthetic/i);
  });
});
