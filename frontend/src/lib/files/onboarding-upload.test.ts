import { afterEach, expect, it, vi } from "vitest";
import { uploadDriverDocument, uploadOnboardingFile } from "./onboarding-upload";
afterEach(() => vi.unstubAllGlobals());
function setup() {
  vi.stubGlobal("crypto", { subtle: { digest: async () => new Uint8Array(32).buffer } });
  const file = new File(["fictional"], "renewal.png", { type: "image/png" });
  Object.defineProperty(file, "arrayBuffer", { value: async () => new ArrayBuffer(9) });
  const fetch = vi
    .fn()
    .mockResolvedValueOnce(
      Response.json({
        upload_id: "upload",
        upload: { url: "http://storage", fields: { key: "private-key" } },
      }),
    )
    .mockResolvedValueOnce(new Response(null, { status: 204 }))
    .mockResolvedValueOnce(Response.json({ id: "file", scan_status: "pending" }))
    .mockResolvedValueOnce(Response.json({ id: "file", scan_status: "clean" }));
  vi.stubGlobal("fetch", fetch);
  return { file, fetch };
}
it("uses owned upload/confirmation/scan routes and leaves signed-in confirmation bodyless", async () => {
  const { file, fetch } = setup();
  expect(await uploadDriverDocument(file, "stable-upload-request", "driver_kyc")).toBe("file");
  expect(fetch.mock.calls[0]![0]).toBe("/api/driver/files/uploads");
  expect(JSON.parse(fetch.mock.calls[0]![1].body).client_request_id).toBe("stable-upload-request");
  expect(fetch.mock.calls[2]).toEqual([
    "/api/driver/files/uploads/upload/confirm",
    { method: "POST", headers: undefined, body: undefined },
  ]);
  expect(fetch.mock.calls[3]).toEqual([
    "/api/driver/files/file",
    { method: "GET", headers: { "content-type": "application/json" }, body: undefined },
  ]);
});
it("retains public capability submission while rejecting unsafe uploaded files", async () => {
  const { file, fetch } = setup();
  fetch
    .mockReset()
    .mockResolvedValueOnce(
      Response.json({ upload_id: "upload", upload: { url: "http://storage", fields: {} } }),
    )
    .mockResolvedValueOnce(new Response(null, { status: 204 }))
    .mockResolvedValueOnce(Response.json({ id: "file" }))
    .mockResolvedValueOnce(Response.json({ scan_status: "infected" }));
  await expect(
    uploadOnboardingFile("private-access", file, "retry", "vehicle_evidence"),
  ).rejects.toThrow(/security checks/);
  expect(JSON.parse(fetch.mock.calls[2]![1].body)).toEqual({
    application_access_token: "private-access",
  });
  expect(fetch.mock.calls[3]![0]).toBe("/api/apply/onboarding/files/file/status");
});
