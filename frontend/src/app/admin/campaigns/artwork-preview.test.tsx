import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
const preview = vi.hoisted(() => vi.fn());
vi.mock("../queue-options", () => ({ previewOperatorArtwork: preview }));
import { ArtworkPreview } from "./artwork-preview";

const SIGNED = "https://storage.example.test/creatives/art.png?X-Amz-Signature=abc";
const createObjectURL = vi.fn(() => "blob:http://localhost/art-1");
const revokeObjectURL = vi.fn();

function storageReturns(body: BodyInit, type: string, status = 200) {
  const fetchMock = vi.fn(
    async () => new Response(body, { status, headers: { "content-type": type } }),
  );
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

beforeEach(() => {
  preview.mockReset();
  createObjectURL.mockClear();
  revokeObjectURL.mockClear();
  Object.assign(URL, { createObjectURL, revokeObjectURL });
});
afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

it("reads signed artwork into a blob: image, never the storage URL, and revokes it after a minute", async () => {
  vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
  preview.mockResolvedValue({ url: SIGNED });
  const fetchMock = storageReturns("png", "image/png");
  render(<ArtworkPreview fileId="file" name="Door wrap" />);
  expect(preview).not.toHaveBeenCalled();
  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name: "View artwork" }));
  });
  expect(preview).toHaveBeenCalledExactlyOnceWith("file");
  expect(fetchMock).toHaveBeenCalledWith(SIGNED, expect.objectContaining({ credentials: "omit" }));
  const image = screen.getByRole("img", { name: "Door wrap" });
  expect(image.getAttribute("src")).toBe("blob:http://localhost/art-1");
  act(() => {
    vi.advanceTimersByTime(60_000);
  });
  expect(screen.queryByRole("img")).toBeNull();
  expect(revokeObjectURL).toHaveBeenCalledWith("blob:http://localhost/art-1");
});

it("shows a loading label while the artwork is being read", async () => {
  let answer!: (value: unknown) => void;
  preview.mockImplementation(() => new Promise((resolve) => (answer = resolve)));
  storageReturns("png", "image/png");
  render(<ArtworkPreview fileId="file" name="Door wrap" />);
  fireEvent.click(screen.getByRole("button", { name: "View artwork" }));
  expect(await screen.findByRole("button", { name: "Opening artwork…" })).toBeDisabled();
  await act(async () => answer({ url: SIGNED }));
  expect(await screen.findByRole("img", { name: "Door wrap" })).toBeVisible();
});

it("offers a PDF as a blob: link instead of a broken image", async () => {
  preview.mockResolvedValue({ url: SIGNED });
  storageReturns("%PDF", "application/pdf");
  render(<ArtworkPreview fileId="file" name="Door wrap" />);
  fireEvent.click(screen.getByRole("button", { name: "View artwork" }));
  const link = await screen.findByRole("link", { name: "Open PDF artwork" });
  expect(link).toHaveAttribute("href", "blob:http://localhost/art-1");
  expect(screen.queryByRole("img")).toBeNull();
});

it("shows a refused preview without inventing an image", async () => {
  preview.mockResolvedValue({ error: "Artwork is unavailable" });
  const fetchMock = storageReturns("png", "image/png");
  render(<ArtworkPreview fileId="file" name="Door wrap" />);
  fireEvent.click(screen.getByRole("button", { name: "View artwork" }));
  await waitFor(() =>
    expect(screen.getByRole("alert")).toHaveTextContent("Artwork is unavailable"),
  );
  expect(fetchMock).not.toHaveBeenCalled();
  expect(screen.queryByRole("img")).toBeNull();
});

it("explains a failed or unexpected storage read", async () => {
  preview.mockResolvedValue({ url: SIGNED });
  storageReturns("<html>", "text/html");
  render(<ArtworkPreview fileId="file" name="Door wrap" />);
  fireEvent.click(screen.getByRole("button", { name: "View artwork" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Artwork preview is unavailable.");
  expect(screen.queryByRole("img")).toBeNull();
  expect(createObjectURL).not.toHaveBeenCalled();
});
