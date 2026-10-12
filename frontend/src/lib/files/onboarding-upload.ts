type UploadResponse = {
  upload_id: string;
  upload: { url: string; fields: Record<string, string> };
};

type StoredFileResponse = { id: string; scan_status: string };

const CODE_NOT_WORKING =
  "This code doesn't work. It may be mistyped, expired or replaced. Get a new code on the first step. Already have sign-in details? Sign in.";
const CHOOSE_FILES_AGAIN = "Please choose your files again, then send.";
const CHECK_DETAILS = "Some details aren't right. Check what you typed, then send again.";

/**
 * Plain words for the onboarding errors an applicant can meet. Every way a code can fail
 * shares one message, as the server does, so the text never reveals which check failed.
 */
const APPLICANT_MESSAGES: Record<string, string> = {
  ONBOARDING_ACCESS_INVALID: CODE_NOT_WORKING,
  PERSON_PAYEE_AUTHORITY_INVALID: CODE_NOT_WORKING,
  VEHICLE_ONBOARDING_AUTHORITY_INVALID: CODE_NOT_WORKING,
  FILE_SCOPE_NOT_FOUND: CODE_NOT_WORKING,
  APPLICATION_UNAVAILABLE: "Applications are closed right now. Please try again later.",
  PERSON_PAYEE_APPROVAL_REQUIRED:
    "Wait until your ID and bank details are approved, then add your car. Check with your application reference on the first step.",
  PERSON_PAYEE_RESUBMISSION_NOT_ALLOWED:
    "We already have your ID and bank details. You can send them again only if we ask for changes.",
  PERSON_PAYEE_RETRY_CONFLICT: CHECK_DETAILS,
  KYC_RETRY_CONFLICT: CHECK_DETAILS,
  VEHICLE_SUBMISSION_RETRY_CONFLICT: CHECK_DETAILS,
  VALIDATION_ERROR: CHECK_DETAILS,
  INVALID_PLATE_NUMBER: "Enter your plate number as it appears on the car.",
  DUPLICATE_VEHICLE_PLATE:
    "A car with this plate number is already registered. Check the plate number.",
  VEHICLE_NOT_FOUND: "We couldn't find that car. Tap Find my cars and choose again.",
  VEHICLE_REVIEW_PENDING: "We're still checking this car. You can send it again after we finish.",
  FILE_UPLOAD_RETRY_CONFLICT: CHOOSE_FILES_AGAIN,
  FILE_UPLOAD_ALREADY_CLOSED: CHOOSE_FILES_AGAIN,
  FILE_UPLOAD_EXPIRED: CHOOSE_FILES_AGAIN,
};

export async function onboardingResponseJson<T>(response: Response): Promise<T> {
  const body = (await response.json().catch(() => null)) as
    T | { error?: { code?: string; message?: string } } | null;
  if (!response.ok) {
    const error = body && typeof body === "object" && "error" in body ? body.error : undefined;
    throw new Error(
      (error?.code ? APPLICANT_MESSAGES[error.code] : undefined) ||
        error?.message ||
        "Something went wrong. Please try again.",
    );
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
      throw new Error(
        "One of your files couldn't be accepted. Choose a different file and try again.",
      );
    }
    await new Promise((resolve) => window.setTimeout(resolve, 1500));
  }
  throw new Error("We're still checking your files. Please try again in a minute.");
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
  if (!uploaded.ok)
    throw new Error("A file didn't upload. Check your internet connection and try again.");
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
