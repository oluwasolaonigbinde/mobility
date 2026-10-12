import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { postJson, uploadInstallationImage } from "./installation-evidence-upload";

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

function photo() {
  return new File([new Uint8Array([1, 2, 3])], "left-side.png", { type: "image/png" });
}

beforeEach(() => {
  vi.stubGlobal("crypto", {
    randomUUID: () => "00000000-0000-4000-8000-000000000001",
    subtle: { digest: async () => new Uint8Array(32).fill(10).buffer },
  });
});
afterEach(() => vi.unstubAllGlobals());

it("returns the private installation file only after its pending scan becomes clean", async () => {
  const fetchMock = vi
    .fn()
    .mockResolvedValueOnce(
      json({
        upload_id: "upload",
        upload: { url: "https://storage.invalid", fields: { key: "private" } },
      }),
    )
    .mockResolvedValueOnce(new Response(null, { status: 204 }))
    .mockResolvedValueOnce(json({ id: "file", scan_status: "pending" }))
    .mockResolvedValueOnce(json({ id: "file", scan_status: "clean" }));
  vi.stubGlobal("fetch", fetchMock);
  await expect(uploadInstallationImage(photo(), { pollDelayMs: 0 })).resolves.toBe("file");
  expect(JSON.parse(String(fetchMock.mock.calls[0]?.[1]?.body))).toMatchObject({
    purpose: "installation_evidence",
    filename: "left-side.png",
    content_type: "image/png",
    sha256: "0a".repeat(32),
  });
  const form = fetchMock.mock.calls[1]?.[1]?.body as FormData;
  expect(form.get("key")).toBe("private");
  expect(form.get("file")).toBeInstanceOf(File);
  expect(fetchMock.mock.calls[3]).toEqual(["/api/driver/files/file", { cache: "no-store" }]);
});

it.each(["infected", "error", "pending"])(
  "refuses an installation image whose scan ends %s",
  async (scanStatus) => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        json({ upload_id: "upload", upload: { url: "https://storage.invalid", fields: {} } }),
      )
      .mockResolvedValueOnce(new Response(null, { status: 204 }))
      .mockResolvedValueOnce(json({ id: "file", scan_status: scanStatus }));
    vi.stubGlobal("fetch", fetchMock);
    await expect(uploadInstallationImage(photo(), { maxPolls: 0 })).rejects.toThrow(
      scanStatus === "infected"
        ? "This photo couldn't be accepted. Take a new photo."
        : "This photo couldn't be checked. Try another photo.",
    );
  },
);

it("reports a failed storage upload without submitting a confirmation", async () => {
  const fetchMock = vi
    .fn()
    .mockResolvedValueOnce(
      json({ upload_id: "upload", upload: { url: "https://storage.invalid", fields: {} } }),
    )
    .mockResolvedValueOnce(new Response(null, { status: 503 }));
  vi.stubGlobal("fetch", fetchMock);
  await expect(uploadInstallationImage(photo())).rejects.toThrow(
    "The photo didn't upload. Try again.",
  );
  expect(fetchMock).toHaveBeenCalledTimes(2);
});

it("uses the generic retry message when an installation request has no error message", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json({ error: {} }, 503)));
  await expect(postJson("/api/driver/installations", { view: "left" })).rejects.toThrow(
    "Something went wrong. Try again.",
  );
});
