import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
const preview = vi.hoisted(() => vi.fn());
vi.mock("../queue-options", () => ({ previewOperatorArtwork: preview }));
import { ArtworkPreview } from "./artwork-preview";
beforeEach(() => {
  preview.mockReset();
});
afterEach(() => {
  vi.useRealTimers();
});
it("requests audited access only when artwork is opened and removes the temporary preview", async () => {
  vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
  preview.mockResolvedValue({ url: "http://127.0.0.1/artwork" });
  render(<ArtworkPreview fileId="file" name="Door wrap" />);
  expect(preview).not.toHaveBeenCalled();
  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name: "View artwork" }));
  });
  expect(preview).toHaveBeenCalledExactlyOnceWith("file");
  expect(screen.getByRole("img", { name: "Door wrap" })).toBeTruthy();
  act(() => {
    vi.advanceTimersByTime(60_000);
  });
  expect(screen.queryByRole("img")).toBeNull();
});
it("shows a refused preview without inventing an image", async () => {
  preview.mockResolvedValue({ error: "Artwork is unavailable" });
  render(<ArtworkPreview fileId="file" name="Door wrap" />);
  fireEvent.click(screen.getByRole("button", { name: "View artwork" }));
  await waitFor(() =>
    expect(screen.getByRole("alert")).toHaveTextContent("Artwork is unavailable"),
  );
  expect(screen.queryByRole("img")).toBeNull();
});
