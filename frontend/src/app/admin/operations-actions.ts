"use server";

import { unstable_rethrow } from "next/navigation";

import { publicActionError } from "@/lib/api/public-action-error";
import { revalidatePath } from "next/cache";
import { createApiClient } from "@/lib/api/client";
import { getSessionToken } from "@/lib/auth/session";
import { ApiError } from "@/lib/api/errors";
import { z } from "zod";
export async function resolveOperation(_state: { error?: string; done?: string }, form: FormData) {
  const parsed = z
    .object({
      kind: z.literal("contact"),
      id: z.string().uuid(),
      note: z.string().trim().min(1).max(2000),
      outcome: z.enum(["attempted", "reached", "failed"]),
      confirmed: z.literal(true),
    })
    .safeParse({
      kind: form.get("kind"),
      id: form.get("id"),
      note: form.get("note"),
      outcome: form.get("outcome") ?? "attempted",
      confirmed: form.get("confirmed") === "on",
    });
  if (!parsed.success) {
    const fields = parsed.error.issues.map((issue) => issue.path[0]);
    return fields.every((field) => field === "note" || field === "confirmed")
      ? { error: "Add a note and tick the box." }
      : { error: "This task couldn't be recorded. Refresh the page and try again." };
  }
  const { id, note, outcome } = parsed.data;
  const api = createApiClient(await getSessionToken());
  try {
    await api.POST("/api/v1/admin/manual-driver-contact-tasks/{task_id}/complete", {
      params: { path: { task_id: id } },
      body: { note, outcome },
    });
    revalidatePath("/admin/support");
    return { done: "Contact recorded." };
  } catch (error) {
    unstable_rethrow(error);
    return {
      error:
        error instanceof ApiError
          ? publicActionError(error)
          : "We couldn't confirm the contact outcome was saved. Refresh the page to check before trying again.",
    };
  }
}
