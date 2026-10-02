import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
const mocks = vi.hoisted(() => ({ search: vi.fn() }));
vi.mock("./global-search-actions", () => ({ searchAdmin: mocks.search }));
import { GlobalSearch } from "./global-search";
beforeEach(() => {
  vi.useFakeTimers();
  mocks.search.mockReset();
});
afterEach(() => {
  vi.useRealTimers();
});
it("waits 300 ms and two characters, exposes named links and closes on Escape", async () => {
  mocks.search.mockResolvedValue([
    { name: "Drivers", items: [{ name: "Ada", href: "/admin/drivers/ada" }] },
  ]);
  render(<GlobalSearch />);
  const input = screen.getByRole("searchbox");
  fireEvent.change(input, { target: { value: "A" } });
  await act(async () => {
    vi.advanceTimersByTime(500);
  });
  expect(mocks.search).not.toHaveBeenCalled();
  fireEvent.change(input, { target: { value: "Ada" } });
  await act(async () => {
    vi.advanceTimersByTime(299);
  });
  expect(mocks.search).not.toHaveBeenCalled();
  await act(async () => {
    vi.advanceTimersByTime(1);
  });
  expect(screen.getByRole("link", { name: "Ada" })).toHaveAttribute("href", "/admin/drivers/ada");
  fireEvent.keyDown(input, { key: "Escape" });
  expect(screen.queryByRole("link", { name: "Ada" })).toBeNull();
});
it("ignores an older result after the query changes", async () => {
  let resolveOld!: (value: unknown) => void;
  mocks.search
    .mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          resolveOld = resolve;
        }),
    )
    .mockResolvedValueOnce([
      { name: "Drivers", items: [{ name: "Musa", href: "/admin/drivers/musa" }] },
    ]);
  render(<GlobalSearch />);
  const input = screen.getByRole("searchbox");
  fireEvent.change(input, { target: { value: "Ada" } });
  await act(async () => {
    vi.advanceTimersByTime(300);
  });
  fireEvent.change(input, { target: { value: "Musa" } });
  await act(async () => {
    vi.advanceTimersByTime(300);
  });
  await act(async () => {
    resolveOld([{ name: "Drivers", items: [{ name: "Ada", href: "/admin/drivers/ada" }] }]);
  });
  expect(screen.getByRole("link", { name: "Musa" })).toBeTruthy();
  expect(screen.queryByRole("link", { name: "Ada" })).toBeNull();
});
it("reports a failed search and hides results when cleared", async () => {
  mocks.search.mockRejectedValue(new Error("down"));
  render(<GlobalSearch />);
  fireEvent.change(screen.getByRole("searchbox"), { target: { value: "Ada" } });
  await act(async () => {
    vi.advanceTimersByTime(300);
  });
  expect(screen.getByRole("alert")).toHaveTextContent("Couldn't load this section — try again");
  fireEvent.change(screen.getByRole("searchbox"), { target: { value: "" } });
  expect(screen.queryByRole("alert")).toBeNull();
});
