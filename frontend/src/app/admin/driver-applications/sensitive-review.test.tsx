import { useState } from "react";
import { act, fireEvent, render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { ReviewDocument, SensitiveReview } from "./sensitive-review";
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

it.each(["success", "failure"])("clears revealed evidence and handles a foreground read %s after hide", async (outcome) => {
  const tab = { opener: window, closed: false, location: { replace: vi.fn() }, close: vi.fn() };
  const open = vi.spyOn(window, "open").mockReturnValue(tab as unknown as Window);
  const visibility = vi.spyOn(document, "visibilityState", "get").mockReturnValue("visible");
  const read = Promise.withResolvers<{ downloadUrl?: string; error?: string }>();
  const readDocument = vi.fn(() => read.promise);
  if (outcome === "failure") {
    open.mockReturnValueOnce(null);
    readDocument.mockResolvedValueOnce({ error: "First read failed" });
  }
  const opened = vi.fn();
  try {
    render(
      <SensitiveReview purpose="Driver application review">
        {(show) => (
          <>
            <button type="button" onClick={show}>Reveal evidence</button>
            <CurrentEvidence />
            <ReviewDocument read={readDocument} onOpened={opened} showFallback={show} />
          </>
        )}
      </SensitiveReview>,
    );
    if (outcome === "failure") {
      fireEvent.click(screen.getByRole("button", { name: "Open document" }));
      expect(await screen.findByRole("alert")).toHaveTextContent("First read failed");
      expect(screen.getByRole("button", { name: "Hide" })).toBeVisible();
    } else {
      fireEvent.click(screen.getByRole("button", { name: "Reveal evidence" }));
    }
    fireEvent.submit(screen.getByRole("button", { name: "View" }).closest("form")!);
    expect(screen.getByText(/Secret NIN/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Open document" }));
    visibility.mockReturnValue("hidden");
    fireEvent(document, new Event("visibilitychange"));
    expect(screen.queryByText(/Secret NIN/)).toBeNull();
    expect(screen.queryByRole("link")).toBeNull();
    expect(tab.close).not.toHaveBeenCalled();

    expect(tab.opener).toBeNull();
    if (outcome === "failure") {
      await act(async () => read.resolve({ error: "Retry read failed" }));
      visibility.mockReturnValue("visible");
      fireEvent(document, new Event("visibilitychange"));
      expect(tab.close).toHaveBeenCalledOnce();
      expect(tab.location.replace).not.toHaveBeenCalled();
      expect(opened).not.toHaveBeenCalled();
      expect(screen.getByRole("alert")).toHaveTextContent("Retry read failed");
    } else {
      await act(async () => read.resolve({ downloadUrl: "https://example.invalid/current" }));
      expect(tab.location.replace).toHaveBeenCalledWith("https://example.invalid/current");
      expect(opened).toHaveBeenCalledOnce();
    }
    expect(screen.queryByRole("link")).toBeNull();
  } finally {
    open.mockRestore();
    visibility.mockRestore();
  }
});
