type UploadResponse = {
  upload_id: string;
  upload: { url: string; fields: Record<string, string> };
};

type StoredFileResponse = { id: string; scan_status: string };

export async function onboardingResponseJson<T>(response: Response): Promise<T> {
  const body = (await response.json().catch(() => null)) as
    T | { error?: { message?: string } } | null;
  if (!response.ok) {
    const message =
      body && typeof body === "object" && "error" in body ? body.error?.message : undefined;
    throw new Error(message || "The onboarding request could not be completed.");
  }
  return body as T;
}

async function sha256(file: File): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", await file.arrayBuffer());
  return Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, "0")).join("");
}

async function waitForClean(accessToken: string, fileId: string): Promise<void> {
  for (let attempt = 0; attempt < 40; attempt += 1) {
    const response = await fetch(`/api/apply/onboarding/files/${fileId}/status`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ application_access_token: accessToken }),
    });
    const file = await onboardingResponseJson<StoredFileResponse>(response);
    if (file.scan_status === "clean") return;
    if (["infected", "rejected"].includes(file.scan_status)) {
      throw new Error("A document did not pass the required security checks.");
    }
    await new Promise((resolve) => window.setTimeout(resolve, 1500));
  }
  throw new Error("Document security checks are still pending. Try again shortly.");
}

// Mirrors the server's per-purpose upload policy (client answer #12).
const ONBOARDING_UPLOAD_POLICY = {
  driver_kyc: { maxBytes: 10 * 1024 * 1024, label: "Identity documents" },
  vehicle_evidence: { maxBytes: 20 * 1024 * 1024, label: "Vehicle documents and photos" },
} as const;
const DOCUMENT_TYPES = new Set(["application/pdf", "image/jpeg", "image/png", "image/webp"]);

export async function uploadOnboardingFile(
  accessToken: string,
  file: File,
  clientRequestId: string,
  purpose: "driver_kyc" | "vehicle_evidence",
): Promise<string> {
  const policy = ONBOARDING_UPLOAD_POLICY[purpose];
  if (!DOCUMENT_TYPES.has(file.type)) throw new Error("Choose a PDF, JPEG, PNG or WebP file.");
  if (file.size <= 0 || file.size > policy.maxBytes) {
    throw new Error(`${policy.label} must be no bigger than ${policy.maxBytes / 1024 / 1024} MB.`);
  }
  const response = await fetch("/api/apply/onboarding/uploads", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      application_access_token: accessToken,
      upload: {
        client_request_id: clientRequestId,
        purpose,
        filename: file.name,
        content_type: file.type,
        size_bytes: file.size,
        sha256: await sha256(file),
      },
    }),
  });
  const intent = await onboardingResponseJson<UploadResponse>(response);
  const form = new FormData();
  for (const [name, value] of Object.entries(intent.upload.fields)) form.append(name, value);
  form.append("file", file);
  const uploaded = await fetch(intent.upload.url, { method: "POST", body: form });
  if (!uploaded.ok) throw new Error("A private document upload failed. Please try again.");
  const confirmed = await onboardingResponseJson<StoredFileResponse>(
    await fetch(`/api/apply/onboarding/uploads/${intent.upload_id}/confirm`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ application_access_token: accessToken }),
    }),
  );
  await waitForClean(accessToken, confirmed.id);
  return confirmed.id;
}
