"use server";
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
  if (!parsed.success)
    return { error: "Confirm the action and provide its reason or recorded contact outcome." };
  const { id, note, outcome } = parsed.data;
  const api = createApiClient(await getSessionToken());
  try {
    await api.POST("/api/v1/admin/manual-driver-contact-tasks/{task_id}/complete", {
      params: { path: { task_id: id } },
      body: { note, outcome },
    });
    revalidatePath("/admin/support");
    return { done: "Contact outcome recorded. This does not confirm provider delivery." };
  } catch (error) {
    return {
      error:
        error instanceof ApiError
          ? error.message
          : "No result was confirmed. Reload or retry the same action and note.",
    };
  }
}
