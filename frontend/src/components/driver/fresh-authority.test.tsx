import { act, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { FreshDriverAuthority } from "./fresh-authority";

function setOnline(value: boolean) {
  Object.defineProperty(navigator, "onLine", { configurable: true, value });
  window.dispatchEvent(new Event(value ? "online" : "offline"));
}

afterEach(() => setOnline(true));

describe("FreshDriverAuthority", () => {
  it("removes already-rendered money and mutation controls on an offline transition", () => {
    setOnline(true);
    render(
      <FreshDriverAuthority
        title="Current earnings hidden while offline"
        detail="Reconnect to load current authority."
        retryHref="/driver/earnings"
      >
        <div>
          <p>₦1,250.00 held</p>
          <button type="button">Submit dispute</button>
        </div>
      </FreshDriverAuthority>,
    );

    expect(screen.getByText("₦1,250.00 held")).toBeInTheDocument();
    act(() => setOnline(false));

    expect(screen.queryByText("₦1,250.00 held")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Submit dispute" })).not.toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent("Current earnings hidden while offline");

    act(() => setOnline(true));
    expect(screen.queryByText("₦1,250.00 held")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Submit dispute" })).not.toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent("Current earnings hidden while offline");
  });
});
