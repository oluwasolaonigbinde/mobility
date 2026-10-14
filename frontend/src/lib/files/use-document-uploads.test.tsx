import { act, renderHook } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { useDocumentUploads } from "./use-document-uploads";

describe("private upload retry identity", () => {
  it.each(["file", "access"])(
    "starts fresh for changed %s identity and keeps retries in their current scope",
    async (change) => {
      const { result } = renderHook(() => useDocumentUploads());
      const file = new File(["document"], "same.png", { type: "image/png" });
      const sibling = new File(["sibling"], "sibling.png", { type: "image/png" });
      const send = vi.fn(async (requestId: string) => `confirmed-${requestId}`);
      let first = "";
      let siblingId = "";
      await act(async () => {
        first = await result.current.upload("licence", file, "first-access", send);
        siblingId = await result.current.upload("photo", sibling, "first-access", send);
      });
      const replacement =
        change === "file" ? new File(["document"], "same.png", { type: "image/png" }) : file;
      const context = change === "access" ? "second-access" : "first-access";
      let next = "";
      let retainedSibling = "";
      await act(async () => {
        next = await result.current.upload("licence", replacement, context, send);
        retainedSibling = await result.current.upload("photo", sibling, context, send);
      });
      expect(next).not.toBe(first);
      if (change === "file") expect(retainedSibling).toBe(siblingId);
      else expect(retainedSibling).not.toBe(siblingId);
      const expectedRequests = change === "file" ? 3 : 4;
      expect(send).toHaveBeenCalledTimes(expectedRequests);
      expect(send.mock.calls[2]![0]).not.toBe(send.mock.calls[0]![0]);
      await act(async () => {
        expect(await result.current.upload("licence", replacement, context, send)).toBe(next);
      });
      expect(send).toHaveBeenCalledTimes(expectedRequests);
    },
  );

  it("refuses a new upload after logout before sending any private document", async () => {
    const { result } = renderHook(() => useDocumentUploads());
    const send = vi.fn(async () => "confirmed-file");
    act(() => window.dispatchEvent(new Event("cardvert-driver-logout")));
    await expect(
      result.current.upload("licence", new File(["private"], "licence.png"), "access", send),
    ).rejects.toThrow("Please sign in again.");
    expect(send).not.toHaveBeenCalled();
  });
});
