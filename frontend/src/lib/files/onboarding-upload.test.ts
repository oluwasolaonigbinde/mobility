import { afterEach, expect, it, vi } from "vitest";
import {
  uploadDriverDocument,
  uploadOnboardingFile,
  type DocumentUploadProgress,
} from "./onboarding-upload";
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

it("coalesces the same running upload and reuses a clean result without more requests", async () => {
  const { file, fetch } = setup();
  const progress = {};
  const first = uploadDriverDocument(file, "stable", "driver_kyc", progress);
  const second = uploadDriverDocument(file, "stable", "driver_kyc", progress);
  expect(await Promise.all([first, second])).toEqual(["file", "file"]);
  expect(await uploadDriverDocument(file, "stable", "driver_kyc", progress)).toBe("file");
  expect(fetch).toHaveBeenCalledTimes(4);
});

it("retries storage on the retained intent when only storage failed", async () => {
  const { file, fetch } = setup();
  const progress = {};
  fetch
    .mockReset()
    .mockResolvedValueOnce(
      Response.json({ upload_id: "original", upload: { url: "http://storage", fields: {} } }),
    )
    .mockResolvedValueOnce(new Response(null, { status: 503 }))
    .mockResolvedValueOnce(new Response(null, { status: 204 }))
    .mockResolvedValueOnce(Response.json({ id: "received", scan_status: "clean" }));
  await expect(uploadDriverDocument(file, "stable", "driver_kyc", progress)).rejects.toThrow(
    "didn't upload",
  );
  expect(await uploadDriverDocument(file, "stable", "driver_kyc", progress)).toBe("received");
  expect(fetch.mock.calls.map(([url]) => url)).toEqual([
    "/api/driver/files/uploads",
    "http://storage",
    "http://storage",
    "/api/driver/files/uploads/original/confirm",
  ]);
});

it.each(["infected", "rejected"])(
  "keeps %s refused without restarting its closed intent",
  async (status) => {
    const { file, fetch } = setup();
    const progress = {};
    fetch
      .mockReset()
      .mockResolvedValueOnce(
        Response.json({ upload_id: "original", upload: { url: "http://storage", fields: {} } }),
      )
      .mockResolvedValueOnce(new Response(null, { status: 204 }))
      .mockResolvedValueOnce(Response.json({ id: "received", scan_status: status }));
    await expect(uploadDriverDocument(file, "stable", "driver_kyc", progress)).rejects.toThrow(
      "different file",
    );
    await expect(uploadDriverDocument(file, "stable", "driver_kyc", progress)).rejects.toThrow(
      "different file",
    );
    expect(fetch).toHaveBeenCalledTimes(3);
  },
);

it.each(["file", "access", "purpose", "request"])(
  "refuses progress reuse across a changed %s identity",
  async (change) => {
    const { file, fetch } = setup();
    const progress = {};
    await uploadOnboardingFile("access", file, "stable", "driver_kyc", progress);
    await expect(
      uploadOnboardingFile(
        change === "access" ? "other" : "access",
        change === "file" ? new File(["fictional"], file.name, { type: file.type }) : file,
        change === "request" ? "other" : "stable",
        change === "purpose" ? "vehicle_evidence" : "driver_kyc",
        progress,
      ),
    ).rejects.toThrow("choose your files again");
    expect(fetch).toHaveBeenCalledTimes(4);
  },
);

it("fences a late intent response before storage upload or confirmation", async () => {
  const { file, fetch } = setup();
  let release!: (response: Response) => void;
  fetch.mockReset().mockImplementationOnce(
    () =>
      new Promise((resolve) => {
        release = resolve;
      }),
  );
  const progress: DocumentUploadProgress = {};
  const pending = uploadDriverDocument(file, "stable", "driver_kyc", progress);
  await vi.waitFor(() => expect(fetch).toHaveBeenCalledTimes(1));
  progress.cancelled = true;
  release(Response.json({ upload_id: "late", upload: { url: "http://storage", fields: {} } }));
  await expect(pending).rejects.toThrow("choose your files again");
  expect(fetch).toHaveBeenCalledTimes(1);
  expect(progress.intent).toBeUndefined();
});

it.each([
  ["driver_kyc", "image/png", 10 * 1024 * 1024 + 1],
  ["vehicle_evidence", "image/png", 20 * 1024 * 1024 + 1],
  ["driver_kyc", "text/plain", 10],
  ["driver_kyc", "image/png", 0],
] as const)("preserves validation before any upload (%s %s %s)", async (purpose, type, size) => {
  const { file, fetch } = setup();
  Object.defineProperty(file, "type", { value: type });
  Object.defineProperty(file, "size", { value: size });
  await expect(uploadDriverDocument(file, "stable", purpose, {})).rejects.toThrow();
  expect(fetch).not.toHaveBeenCalled();
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
  ).rejects.toThrow(
    "One of your files couldn't be accepted. Choose a different file and try again.",
  );
  expect(JSON.parse(fetch.mock.calls[2]![1].body)).toEqual({
    application_access_token: "private-access",
  });
  expect(fetch.mock.calls[3]![0]).toBe("/api/apply/onboarding/files/file/status");
});

it("resumes only scan polling after a confirmed upload loses its status response", async () => {
  const { file, fetch } = setup();
  const progress = {};
  fetch
    .mockReset()
    .mockResolvedValueOnce(
      Response.json({ upload_id: "original", upload: { url: "http://storage", fields: {} } }),
    )
    .mockResolvedValueOnce(new Response(null, { status: 204 }))
    .mockResolvedValueOnce(Response.json({ id: "received", scan_status: "pending" }))
    .mockRejectedValueOnce(new Error("offline"))
    .mockResolvedValueOnce(Response.json({ id: "received", scan_status: "clean" }));
  await expect(
    uploadOnboardingFile("access", file, "stable", "driver_kyc", progress),
  ).rejects.toThrow("offline");
  expect(await uploadOnboardingFile("access", file, "stable", "driver_kyc", progress)).toBe(
    "received",
  );
  expect(fetch.mock.calls.map(([url]) => url)).toEqual([
    "/api/apply/onboarding/uploads",
    "http://storage",
    "/api/apply/onboarding/uploads/original/confirm",
    "/api/apply/onboarding/files/received/status",
    "/api/apply/onboarding/files/received/status",
  ]);
});

it("reconfirms the same intent after a lost confirmation response without uploading again", async () => {
  const { file, fetch } = setup();
  const progress = {};
  fetch
    .mockReset()
    .mockResolvedValueOnce(
      Response.json({ upload_id: "original", upload: { url: "http://storage", fields: {} } }),
    )
    .mockResolvedValueOnce(new Response(null, { status: 204 }))
    .mockRejectedValueOnce(new Error("response lost"))
    .mockResolvedValueOnce(Response.json({ id: "received", scan_status: "clean" }));
  await expect(uploadDriverDocument(file, "stable", "driver_kyc", progress)).rejects.toThrow(
    "response lost",
  );
  expect(await uploadDriverDocument(file, "stable", "driver_kyc", progress)).toBe("received");
  expect(fetch.mock.calls.map(([url]) => url)).toEqual([
    "/api/driver/files/uploads",
    "http://storage",
    "/api/driver/files/uploads/original/confirm",
    "/api/driver/files/uploads/original/confirm",
  ]);
});
