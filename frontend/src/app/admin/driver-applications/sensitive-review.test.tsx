import { act, fireEvent, render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { SensitiveReview } from "./sensitive-review";
it("requires purpose and confirmation and removes protected content on hide and timeout", () => {
  vi.useFakeTimers();
  render(
    <SensitiveReview purpose="Person approval">
      <p>Protected identity</p>
    </SensitiveReview>,
  );
  expect(screen.queryByText("Protected identity")).toBeNull();
  expect(screen.getByRole("button", { name: /Confirm/ })).toBeDisabled();
  fireEvent.change(screen.getByLabelText("Review purpose"), {
    target: { value: "Person approval" },
  });
  fireEvent.click(screen.getByRole("checkbox"));
  fireEvent.click(screen.getByRole("button", { name: /Confirm/ }));
  expect(screen.getByText("Protected identity")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Hide protected evidence" }));
  expect(screen.queryByText("Protected identity")).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: /Confirm/ }));
  act(() => vi.advanceTimersByTime(60_000));
  expect(screen.queryByText("Protected identity")).toBeNull();
  vi.useRealTimers();
});
