import { useState } from "react";
import { act, fireEvent, render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { SensitiveReview } from "./sensitive-review";
function CurrentEvidence() {
  const [visible, setVisible] = useState(false);
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        setVisible(true);
      }}
    >
      <button type="submit">View</button>
      {visible ? (
        <>
          <p>Secret NIN and bank details</p>
          <a href="https://example.invalid/private">Document link</a>
        </>
      ) : null}
    </form>
  );
}

it.each(["timeout", "pagehide", "visibilitychange", "manual"])(
  "direct review hides and resets each read after %s",
  (event) => {
    vi.useFakeTimers();
    render(
      <SensitiveReview purpose="Identity review">
        <CurrentEvidence />
      </SensitiveReview>,
    );
    expect(screen.getByRole("button", { name: "View" })).toBeEnabled();
    expect(screen.queryByText(/Secret NIN/)).toBeNull();
    fireEvent.submit(screen.getByRole("button", { name: "View" }).closest("form")!);
    expect(screen.getByText(/Secret NIN/)).toBeInTheDocument();
    if (event === "timeout") act(() => vi.advanceTimersByTime(60000));
    else if (event === "manual") fireEvent.click(screen.getByRole("button", { name: "Hide" }));
    else if (event === "pagehide") fireEvent(window, new Event("pagehide"));
    else {
      Object.defineProperty(document, "visibilityState", { configurable: true, value: "hidden" });
      fireEvent(document, new Event("visibilitychange"));
      Object.defineProperty(document, "visibilityState", { configurable: true, value: "visible" });
    }
    expect(screen.queryByText(/Secret NIN/)).toBeNull();
    expect(screen.queryByRole("link")).toBeNull();
    expect(screen.queryByRole("checkbox")).toBeNull();
    expect(screen.getByRole("button", { name: "View" })).toBeEnabled();
    vi.useRealTimers();
  },
);

it("restarts the minute limit for every explicit read attempt", () => {
  vi.useFakeTimers();
  render(
    <SensitiveReview purpose="Driver application review">
      <CurrentEvidence />
    </SensitiveReview>,
  );
  const read = () =>
    fireEvent.submit(screen.getByRole("button", { name: "View" }).closest("form")!);
  read();
  act(() => vi.advanceTimersByTime(45000));
  read();
  act(() => vi.advanceTimersByTime(15000));
  expect(screen.getByText(/Secret NIN/)).toBeInTheDocument();
  act(() => vi.advanceTimersByTime(45000));
  expect(screen.queryByText(/Secret NIN/)).toBeNull();
  vi.useRealTimers();
});
