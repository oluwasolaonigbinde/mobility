import { ApiError } from "@/lib/api/errors";

/** The account page shows only this fixed copy; the URL carries a code, never text. */
const COMPANY_UPDATE_ERRORS = {
  busy: "This page is busy. Try again in a moment.",
  failed: "That didn't work. Please try again.",
  unavailable: "Could not update company profile",
} as const;

export type CompanyUpdateError = keyof typeof COMPANY_UPDATE_ERRORS;

export function companyUpdateErrorCode(error: unknown): CompanyUpdateError {
  if (!(error instanceof ApiError)) return "unavailable";
  return error.code === "TRY_AGAIN_SOON" ? "busy" : "failed";
}

export function companyUpdateErrorCopy(code: unknown): string | null {
  return typeof code === "string" && Object.hasOwn(COMPANY_UPDATE_ERRORS, code)
    ? COMPANY_UPDATE_ERRORS[code as CompanyUpdateError]
    : null;
}
