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
      {
        pollDelayMs: 0,
        clientRequestId: "00000000-0000-4000-8000-000000000099",
      },
    );

    expect(result).toEqual({ storedFileId: "file-1", creativeType: "image" });
    expect(phases).toEqual(["hashing", "uploading", "scanning", "clean"]);
    expect(JSON.parse(String(fetchMock.mock.calls[0]?.[1]?.body)).client_request_id).toBe(
      "00000000-0000-4000-8000-000000000099",
    );
    const directUpload = fetchMock.mock.calls[1];
    expect(directUpload?.[0]).toBe("http://storage");
    expect(directUpload?.[1]?.body).toBeInstanceOf(FormData);
    expect((directUpload?.[1]?.body as FormData).get("key")).toBe("k");
    expect((directUpload?.[1]?.body as FormData).get("file")).toBeInstanceOf(File);
  });

  it("never exposes backend error text", async () => {
    vi.stubGlobal("crypto", {
      randomUUID: () => "00000000-0000-4000-8000-000000000001",
      subtle: { digest: async () => new Uint8Array(32).buffer },
    });
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValueOnce(
          json({ error: { message: "storage host secret.internal failed" } }, 500),
        ),
    );

    await expect(
      uploadCreativeFile(
        new File([new Uint8Array([1])], "wrap.png", { type: "image/png" }),
        () => undefined,
      ),
    ).rejects.toThrow("The file request failed. Retry the upload.");
  });

  it("resumes confirmation after its committed response is lost", async () => {
    vi.stubGlobal("crypto", {
      randomUUID: () => "00000000-0000-4000-8000-000000000001",
      subtle: { digest: async () => new Uint8Array(32).fill(10).buffer },
    });
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        json({ upload_id: "upload-lost", upload: { url: "http://storage", fields: {} } }),
      )
      .mockResolvedValueOnce(new Response(null, { status: 204 }))
      .mockRejectedValueOnce(new TypeError("response lost after commit"))
      .mockResolvedValueOnce(json({ id: "file-lost", scan_status: "clean" }, 201));
    vi.stubGlobal("fetch", fetchMock);
    const file = new File([new Uint8Array([1, 2, 3])], "wrap.png", { type: "image/png" });
    const options = {
      pollDelayMs: 0,
      clientRequestId: "00000000-0000-4000-8000-000000000099",
    };

    await expect(uploadCreativeFile(file, () => undefined, options)).rejects.toThrow(
      "response lost after commit",
    );
    await expect(uploadCreativeFile(file, () => undefined, options)).resolves.toEqual({
      storedFileId: "file-lost",
      creativeType: "image",
    });

    expect(fetchMock).toHaveBeenCalledTimes(4);
    expect(
      fetchMock.mock.calls.filter(([url]) => url === "/api/advertiser/files/uploads"),
    ).toHaveLength(1);
    expect(fetchMock.mock.calls.filter(([url]) => url === "http://storage")).toHaveLength(1);
    expect(fetchMock.mock.calls[3]?.[0]).toBe("/api/advertiser/files/uploads/upload-lost/confirm");
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
