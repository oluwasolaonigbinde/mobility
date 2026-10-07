"use server";
import { z } from "zod";
import { createApiClient } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import { getSessionToken } from "@/lib/auth/session";

export type PhoneVerificationState = { error?: string; done?: string };
export async function recordPhoneVerificationAction(
  _previous: PhoneVerificationState,
  form: FormData,
): Promise<PhoneVerificationState> {
  const parsed = z
    .object({
      driver_profile_id: z.string().uuid(),
      challenge_id: z.string().uuid(),
      code: z.string().regex(/^[0-9]{6}$/),
      sender_phone: z.string().trim().min(8).max(32),
    })
    .safeParse(Object.fromEntries(form));
  if (!parsed.success)
    return { error: "Enter the six-digit code and the number the message came from." };
  try {
    await createApiClient(await getSessionToken()).POST(
      "/api/v1/admin/drivers/{driver_profile_id}/phone-verification",
      {
        params: { path: { driver_profile_id: parsed.data.driver_profile_id } },
        body: {
          challenge_id: parsed.data.challenge_id,
          code: parsed.data.code,
          sender_phone: parsed.data.sender_phone,
        },
      },
    );
  } catch (e) {
    return {
      error:
        e instanceof ApiError
          ? e.message
          : "Couldn't record verification. Check the phone status before trying again.",
    };
  }
  return { done: "Phone verified. Contact tasks still need the driver's current consent." };
}
