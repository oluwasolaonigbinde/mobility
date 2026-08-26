const MAX_CREATIVE_BYTES = 25 * 1024 * 1024;
const ACCEPTED_TYPES = new Set([
  "application/pdf",
  "image/jpeg",
  "image/png",
  "image/webp",
  "video/mp4",
]);

export type CreativeUploadPhase = "hashing" | "uploading" | "scanning" | "clean";

type UploadIntent = {
  upload_id: string;
  upload: { url: string; fields: Record<string, string> };
};

type StoredFile = {
  id: string;
  scan_status: "pending" | "clean" | "infected" | "rejected" | "error";
};

async function responseJson<T>(response: Response): Promise<T> {
  const body = (await response.json()) as T & { error?: { message?: string } };
  if (!response.ok) throw new Error(body.error?.message ?? "The file request failed.");
  return body;
}

async function sha256(file: File): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", await file.arrayBuffer());
  return Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, "0")).join("");
}

function scanFailure(status: StoredFile["scan_status"]): Error {
  if (status === "infected")
    return new Error("Malware was detected. Remove this file and try another.");
  if (status === "rejected")
    return new Error("The file content does not match an allowed creative format.");
  return new Error("The security scan could not complete. Retry the upload.");
}

export async function uploadCreativeFile(
  file: File,
  onPhase: (phase: CreativeUploadPhase) => void,
  options: { pollDelayMs?: number; maxPolls?: number } = {},
): Promise<{ storedFileId: string; creativeType: "image" | "video" | "other" }> {
  if (!ACCEPTED_TYPES.has(file.type))
    throw new Error("Choose a PNG, JPEG, WebP, MP4, or PDF file.");
  if (file.size <= 0 || file.size > MAX_CREATIVE_BYTES) {
    throw new Error("Creative files must be larger than 0 bytes and no more than 25 MB.");
  }

  onPhase("hashing");
  const checksum = await sha256(file);
  const intent = await responseJson<UploadIntent>(
    await fetch("/api/advertiser/files/uploads", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        client_request_id: crypto.randomUUID(),
        purpose: "creative",
        filename: file.name,
        content_type: file.type,
        size_bytes: file.size,
        sha256: checksum,
      }),
    }),
  );

  onPhase("uploading");
  const form = new FormData();
  for (const [name, value] of Object.entries(intent.upload.fields)) form.append(name, value);
  form.append("file", file);
  const uploaded = await fetch(intent.upload.url, { method: "POST", body: form });
  if (!uploaded.ok) throw new Error("The private file upload failed. Retry the upload.");

  let stored = await responseJson<StoredFile>(
    await fetch(`/api/advertiser/files/uploads/${intent.upload_id}/confirm`, { method: "POST" }),
  );
  onPhase("scanning");
  const maxPolls = options.maxPolls ?? 40;
  const pollDelayMs = options.pollDelayMs ?? 1500;
  for (let attempt = 0; stored.scan_status === "pending" && attempt < maxPolls; attempt += 1) {
    await new Promise((resolve) => setTimeout(resolve, pollDelayMs));
    stored = await responseJson<StoredFile>(
      await fetch(`/api/advertiser/files/${stored.id}`, { cache: "no-store" }),
    );
  }
  if (stored.scan_status === "pending") {
    throw new Error("The security scan is still pending. Retry this upload in a moment.");
  }
  if (stored.scan_status !== "clean") throw scanFailure(stored.scan_status);
  onPhase("clean");
  return {
    storedFileId: stored.id,
    creativeType: file.type.startsWith("image/")
      ? "image"
      : file.type.startsWith("video/")
        ? "video"
        : "other",
  };
}
