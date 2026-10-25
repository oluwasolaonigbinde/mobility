"use server";

import { unstable_rethrow } from "next/navigation";

import { publicActionError } from "@/lib/api/public-action-error";
import { revalidatePath } from "next/cache";
import { createApiClient } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import { getSessionToken } from "@/lib/auth/session";
import { requireRole } from "@/lib/auth/current-user";

export type InviteState = { error?: string; done?: string };

export async function sendLoginInviteAction(
  organizationId: string,
  _state: InviteState,
  form: FormData,
): Promise<InviteState> {
  await requireRole("admin");
  try {
    await createApiClient(await getSessionToken()).POST(
      "/api/v1/admin/advertiser-organizations/{organization_id}/login-invite",
      {
        params: { path: { organization_id: organizationId } },
        body: { email: String(form.get("email") ?? "").trim() },
      },
    );
  } catch (error) {
    unstable_rethrow(error);
    return {
      error:
        error instanceof ApiError
          ? publicActionError(error)
          : "The invite couldn't be sent. Try again.",
    };
  }
  revalidatePath(`/admin/advertisers/${organizationId}`);
  return { done: "Login invite sent. It works once, for 24 hours." };
}
