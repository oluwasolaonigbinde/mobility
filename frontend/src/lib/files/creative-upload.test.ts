import { afterEach, describe, expect, it, vi } from "vitest";
import { uploadCreativeFile } from "./creative-upload";

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

describe("uploadCreativeFile", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("hashes, uploads privately, confirms, and waits for a clean scan", async () => {
    vi.stubGlobal("crypto", {
      randomUUID: () => "00000000-0000-4000-8000-000000000001",
      subtle: { digest: async () => new Uint8Array(32).fill(10).buffer },
    });
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        json({ upload_id: "upload-1", upload: { url: "http://storage", fields: { key: "k" } } }),
      )
      .mockResolvedValueOnce(new Response(null, { status: 204 }))
      .mockResolvedValueOnce(json({ id: "file-1", scan_status: "pending" }, 201))
      .mockResolvedValueOnce(json({ id: "file-1", scan_status: "clean" }));
    vi.stubGlobal("fetch", fetchMock);
    const phases: string[] = [];

    const result = await uploadCreativeFile(
      new File([new Uint8Array([1, 2, 3])], "wrap.png", { type: "image/png" }),
      (phase) => phases.push(phase),
      { pollDelayMs: 0 },
    );

    expect(result).toEqual({ storedFileId: "file-1", creativeType: "image" });
    expect(phases).toEqual(["hashing", "uploading", "scanning", "clean"]);
    const directUpload = fetchMock.mock.calls[1];
    expect(directUpload?.[0]).toBe("http://storage");
    expect(directUpload?.[1]?.body).toBeInstanceOf(FormData);
    expect((directUpload?.[1]?.body as FormData).get("key")).toBe("k");
    expect((directUpload?.[1]?.body as FormData).get("file")).toBeInstanceOf(File);
  });

  it("fails closed on an infected scan and rejects unsupported input before network use", async () => {
    vi.stubGlobal("crypto", {
      randomUUID: () => "00000000-0000-4000-8000-000000000001",
      subtle: { digest: async () => new Uint8Array(32).buffer },
    });
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        json({ upload_id: "upload-1", upload: { url: "http://storage", fields: {} } }),
      )
      .mockResolvedValueOnce(new Response(null, { status: 204 }))
      .mockResolvedValueOnce(json({ id: "file-1", scan_status: "infected" }, 201));
    vi.stubGlobal("fetch", fetchMock);

    await expect(
      uploadCreativeFile(
        new File([new Uint8Array([1])], "bad.png", { type: "image/png" }),
        () => undefined,
      ),
    ).rejects.toThrow("Malware was detected");
    await expect(
      uploadCreativeFile(
        new File([new Uint8Array([1])], "bad.svg", { type: "image/svg+xml" }),
        () => undefined,
      ),
    ).rejects.toThrow("Choose a PNG");
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });
});
