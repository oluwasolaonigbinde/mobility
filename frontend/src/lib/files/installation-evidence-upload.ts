const MAX_IMAGE_BYTES = 25 * 1024 * 1024;
const ACCEPTED_TYPES = new Set(["image/jpeg", "image/png", "image/webp"]);

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
  if (!response.ok) throw new Error(body.error?.message ?? "The evidence request failed.");
  return body;
}

async function sha256(file: File): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", await file.arrayBuffer());
  return Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, "0")).join("");
}

export async function uploadInstallationImage(
  file: File,
  options: { pollDelayMs?: number; maxPolls?: number } = {},
): Promise<string> {
  if (!ACCEPTED_TYPES.has(file.type)) throw new Error("Choose a PNG, JPEG, or WebP image.");
  if (file.size <= 0 || file.size > MAX_IMAGE_BYTES) {
    throw new Error("Evidence images must be larger than 0 bytes and no more than 25 MB.");
  }
  const intent = await responseJson<UploadIntent>(
    await fetch("/api/driver/files/uploads", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        client_request_id: crypto.randomUUID(),
        purpose: "installation_evidence",
        filename: file.name,
        content_type: file.type,
        size_bytes: file.size,
        sha256: await sha256(file),
      }),
    }),
  );
  const form = new FormData();
  for (const [name, value] of Object.entries(intent.upload.fields)) form.append(name, value);
  form.append("file", file);
  const uploaded = await fetch(intent.upload.url, { method: "POST", body: form });
  if (!uploaded.ok) throw new Error("The private evidence upload failed. Retry the upload.");

  let stored = await responseJson<StoredFile>(
    await fetch(`/api/driver/files/uploads/${intent.upload_id}/confirm`, { method: "POST" }),
  );
  const maxPolls = options.maxPolls ?? 40;
  const pollDelayMs = options.pollDelayMs ?? 1500;
  for (let attempt = 0; stored.scan_status === "pending" && attempt < maxPolls; attempt += 1) {
    await new Promise((resolve) => setTimeout(resolve, pollDelayMs));
    stored = await responseJson<StoredFile>(
      await fetch(`/api/driver/files/${stored.id}`, { cache: "no-store" }),
    );
  }
  if (stored.scan_status === "infected") throw new Error("Malware was detected in this image.");
  if (stored.scan_status !== "clean") {
    throw new Error("The evidence image did not pass its security scan. Retry with another image.");
  }
  return stored.id;
}

export async function postJson<T>(path: string, body: unknown): Promise<T> {
  return responseJson<T>(
    await fetch(path, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(body),
    }),
  );
}
